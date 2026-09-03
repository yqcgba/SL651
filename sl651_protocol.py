"""
SL651-2014 水文监测数据通信规约 - 协议编码模块

实现 HEX/BCD 编码方式，支持 M1（发送/无回答）传输模式
功能码 32H：遥测站定时报

参考文献：
  SL/T 651-2014 水文监测数据通信规约
"""

import struct
from datetime import datetime


# ===================== 常量定义 =====================

# 帧控制字符
FRAME_START_HEX = b'\x7e\x7e'       # HEX/BCD编码帧起始符
STX = b'\x02'                        # 传输正文起始
ETX = b'\x03'                        # 报文结束，无后续报文
ETB = b'\x17'                        # 报文结束，有后续报文
ENQ = b'\x05'                        # 询问
EOT = b'\x04'                        # 传输结束
ACK = b'\x06'                        # 肯定确认
NAK = b'\x15'                        # 否定应答
SYN = b'\x16'                        # 多包传输正文起始

# 标识符引导符（HEX/BCD编码）
GUIDE_OBS_TIME = 0xF0                # 观测时间引导符
GUIDE_STATION_ADDR = 0xF1            # 测站地址引导符
GUIDE_PN = 0x20                      # 时段降水量
GUIDE_PN05 = 0x22                    # 5分钟时段降水量
GUIDE_PN10 = 0x23                    # 小时降水量
GUIDE_PN15 = 0x24                    # 连续降水量
GUIDE_PS = 0x25                      # 暴雨量
GUIDE_PT = 0x26                      # 降水量累计值
GUIDE_Z = 0x39                       # 瞬时河道水位、潮位
GUIDE_ZU = 0x3B                      # 库(闸、站)上水位
GUIDE_VOLTAGE = 0x38                 # 电源电压
GUIDE_TIME_STEP = 0x04               # 时间步长码
GUIDE_FLOW = 0x60                    # 瞬时流量
GUIDE_TA = 0xA4                      # 气温
GUIDE_WS = 0xA2                      # 风速

# 功能码
FUNC_LINK_KEEP = 0x2F                # 链路维持报
FUNC_TEST = 0x30                     # 测试报
FUNC_UNIFORM = 0x31                  # 均匀时段水文信息报
FUNC_TIMED = 0x32                    # 遥测站定时报
FUNC_ALARM = 0x33                    # 遥测站加报报
FUNC_HOURLY = 0x34                   # 遥测站小时报
FUNC_MANUAL = 0x35                   # 遥测站人工置数报
FUNC_PICTURE = 0x36                  # 查询/报送JPG图片信息
FUNC_QUERY_REALTIME = 0x37           # 查询实时数据
FUNC_QUERY_PERIOD = 0x38             # 查询时段数据

# 遥测站分类码
STATION_TYPES = {
    '降水': 0x50,    # P
    '河道': 0x48,    # H
    '水库(湖泊)': 0x4B,  # K
    '闸坝': 0x5A,    # Z
    '泵站': 0x44,    # D
    '潮汐': 0x54,    # T
    '墒情': 0x4D,    # M
    '地下水': 0x47,  # G
    '水质': 0x51,    # Q
    '取水口': 0x49,  # I
    '排水口': 0x4F,  # O
}

# 标识符参考全表 (附录C 遥测信息编码要素标识符)
# 格式: {名称: (引导符, 数据总位数, 小数位数, 单位)}
ELEMENT_REFS = {
    # 降水量要素
    'P (时段降水量)':           (0x20, 5, 1, 'mm'),
    'PN05 (5分钟时段降水量)':   (0x22, 5, 1, 'mm'),
    'PL05 (5分钟降水量累计值)': (0x26, 5, 1, 'mm'),
    'PT (降水量累计值)':        (0x26, 5, 1, 'mm'),
    
    # 河道水位
    'Z (瞬时河道水位)':         (0x39, 7, 3, 'm'),
    'ZG (河道预警水位)':        (0x34, 7, 3, 'm'),
    'ZB (河道保证水位)':        (0x36, 7, 3, 'm'),
    
    # 库水位
    'ZU (库/闸/站上水位)':      (0x3B, 7, 3, 'm'),
    'ZD (库/闸/站下水位)':      (0x4B, 7, 3, 'm'),
    'ZK (库内水位)':            (0x3E, 7, 3, 'm'),
    
    # 潮位
    'HT (瞬时潮位)':            (0x39, 7, 3, 'm'),
    
    # 闸门
    'GH (闸门开启高度)':        (0x50, 5, 2, 'm'),
    'GN (闸门开启孔数)':        (0x51, 3, 0, '孔'),
    'GT (闸门总孔数)':          (0x52, 3, 0, '孔'),
    
    # 流量
    'Q (瞬时流量)':             (0x60, 9, 3, 'm³/s'),
    'QS (流量累积值)':          (0x62, 9, 3, '万m³'),
    
    # 流速
    'V (断面平均流速)':         (0x55, 5, 3, 'm/s'),
    'VM (最大流速)':            (0x56, 5, 3, 'm/s'),
    
    # 蒸发/含沙/水温
    'ES (日蒸发量)':            (0x71, 5, 1, 'mm'),
    'CS (含沙量)':              (0x75, 7, 3, 'kg/m³'),
    'TW (水温)':                (0x78, 4, 1, '℃'),
    
    # 地下水
    'W (地下水埋深)':           (0x80, 7, 3, 'm'),
    'WL (地下水水位)':          (0x81, 7, 3, 'm'),
    
    # 土壤墒情
    'SS (土壤含水率)':          (0x90, 4, 1, '%'),
    
    # 气象要素
    'WD (风向)':                (0xA1, 3, 0, '°'),
    'WS (风速)':                (0xA2, 5, 2, 'm/s'),
    'TA (气温)':                (0xA4, 4, 1, '℃'),
    'RH (相对湿度)':            (0xA6, 4, 1, '%'),
    'PA (气压)':                (0xA8, 5, 1, 'hPa'),
    'ESV (水面蒸发量)':         (0xAB, 5, 1, 'mm'),
    
    # 风力风向
    'FB (蒲福风力等级)':        (0xAC, 2, 0, '级'),
    
    # 水质
    'PH (pH值)':                (0xB1, 4, 2, ''),
    'DO (溶解氧)':              (0xB2, 4, 1, 'mg/L'),
    'COD (化学需氧量)':         (0xB3, 5, 1, 'mg/L'),
    'NH3N (氨氮)':              (0xB4, 5, 2, 'mg/L'),
    'TP (总磷)':                (0xB6, 5, 3, 'mg/L'),
    'TN (总氮)':                (0xB7, 5, 2, 'mg/L'),
    'TB (浊度)':                (0xB8, 5, 1, 'NTU'),
    'COND (电导率)':            (0xB9, 5, 1, 'μS/cm'),
    'CHL (叶绿素a)':            (0xBA, 5, 1, 'μg/L'),
}

# 标识符及数据定义（简表 - 上述全表中提取常用）
# 格式: (引导符, 数据总位数, 小数位数)
ELEMENT_DEFS = {
    'PN05': (GUIDE_PN05, 5, 1),     # 5分钟时段降水量 N(5,1) mm
    'Z': (GUIDE_Z, 7, 3),           # 瞬时河道水位 N(7,3) m
    'ZU': (GUIDE_ZU, 7, 3),         # 库(闸、站)上水位 N(7,3) m
}

# 按引导符(要素ID)索引的完整要素定义表
# 格式: {引导符: (要素名称, 数据总位数, 小数位数, 单位)}
# 用于通过要素ID [22], [38] 等快速查找标准定义
ELEMENT_BY_GUIDE = {
    # 降水量要素
    0x20: ('时段降水量 P', 5, 1, 'mm'),
    0x21: ('日降水量 PD', 5, 1, 'mm'),
    0x22: ('5分钟时段降水量 PN05', 5, 1, 'mm'),
    0x23: ('小时降水量 PH', 5, 1, 'mm'),
    0x24: ('连续降水量 PC', 5, 1, 'mm'),
    0x25: ('暴雨量 PS', 5, 1, 'mm'),
    0x26: ('降水量累计值 PT', 5, 1, 'mm'),
    0x27: ('降雪量 SN', 5, 1, 'mm'),
    0x28: ('时段降水量差值 PDV', 5, 1, 'mm'),

    # 河道水位
    0x30: ('河道水位 Z', 7, 3, 'm'),
    0x31: ('河道冻结水位 ZFZ', 7, 3, 'm'),
    0x32: ('河道警戒水位 ZG', 7, 3, 'm'),
    0x33: ('河道保证水位 ZB', 7, 3, 'm'),
    0x34: ('河道警戒水位(提前) ZGX', 7, 3, 'm'),
    0x35: ('河道超限水位 ZC', 7, 3, 'm'),
    0x36: ('河道保证水位(提前) ZBX', 7, 3, 'm'),
    0x37: ('河道特征水位 ZT', 7, 3, 'm'),
    0x38: ('电源电压 V', 4, 2, 'V'),
    0x39: ('瞬时河道水位 Z', 7, 3, 'm'),
    0x3A: ('瞬时潮位 HT', 7, 3, 'm'),
    0x3B: ('库(闸/站)上水位 ZU', 7, 3, 'm'),
    0x3C: ('水库汛限水位 ZL', 7, 3, 'm'),
    0x3D: ('水库死水位 ZDIE', 7, 3, 'm'),
    0x3E: ('库内水位 ZK', 7, 3, 'm'),
    0x3F: ('坝上水位 ZDB', 7, 3, 'm'),

    # 闸坝水位
    0x40: ('闸上水位 ZGUP', 7, 3, 'm'),
    0x41: ('闸下水位 ZGLO', 7, 3, 'm'),
    0x42: ('坝下水位 ZDBLO', 7, 3, 'm'),
    0x43: ('泵站前池水位 ZBP', 7, 3, 'm'),
    0x44: ('泵站出水池水位 ZEP', 7, 3, 'm'),
    0x45: ('取水口水位 ZQ', 7, 3, 'm'),
    0x46: ('排水口水位 ZP', 7, 3, 'm'),
    0x47: ('潮位站潮位 HTT', 7, 3, 'm'),
    0x48: ('河道站潮位 HTR', 7, 3, 'm'),
    0x49: ('库(湖)站潮位 HTL', 7, 3, 'm'),
    0x4A: ('闸下潮位 GTLO', 7, 3, 'm'),
    0x4B: ('库/闸/站下水位 ZD', 7, 3, 'm'),
    0x50: ('闸门开启高度 GH', 5, 2, 'm'),
    0x51: ('闸门开启孔数 GN', 3, 0, '孔'),
    0x52: ('闸门总孔数 GT', 3, 0, '孔'),
    0x53: ('闸门开度 GD', 5, 2, 'm'),

    # 流量/流速
    0x55: ('断面平均流速 V', 5, 3, 'm/s'),
    0x56: ('最大流速 VM', 5, 3, 'm/s'),
    0x57: ('断面平均流速 VE', 5, 3, 'm/s'),
    0x60: ('瞬时流量 Q', 9, 3, 'm³/s'),
    0x61: ('时段平均流量 QP', 9, 3, 'm³/s'),
    0x62: ('流量累积值 QS', 9, 3, '万m³'),
    0x63: ('时段最大流量 QMAX', 9, 3, 'm³/s'),
    0x65: ('入库流量 QIN', 9, 3, 'm³/s'),
    0x66: ('出库流量 QOUT', 9, 3, 'm³/s'),

    # 蒸发/含沙/水温
    0x70: ('水面蒸发量 EV', 5, 1, 'mm'),
    0x71: ('日蒸发量 ES', 5, 1, 'mm'),
    0x72: ('旬蒸发量 EX', 5, 1, 'mm'),
    0x73: ('月蒸发量 EM', 5, 1, 'mm'),
    0x75: ('含沙量 CS', 7, 3, 'kg/m³'),
    0x78: ('水温 TW', 4, 1, '℃'),

    # 地下水
    0x80: ('地下水埋深 W', 7, 3, 'm'),
    0x81: ('地下水水位 WL', 7, 3, 'm'),
    0x82: ('地下水水温 GWT', 4, 1, '℃'),

    # 土壤墒情
    0x90: ('土壤含水率 SS', 4, 1, '%'),
    0x91: ('土壤温度 ST', 4, 1, '℃'),

    # 气象要素
    0xA0: ('日照时数 SD', 4, 1, 'h'),
    0xA1: ('风向 WD', 3, 0, '°'),
    0xA2: ('风速 WS', 5, 2, 'm/s'),
    0xA3: ('最大风速 WSM', 5, 2, 'm/s'),
    0xA4: ('气温 TA', 4, 1, '℃'),
    0xA5: ('最高气温 TAMAX', 4, 1, '℃'),
    0xA6: ('相对湿度 RH', 4, 1, '%'),
    0xA7: ('最低气温 TAMIN', 4, 1, '℃'),
    0xA8: ('气压 PA', 5, 1, 'hPa'),
    0xA9: ('地面温度 GTMP', 4, 1, '℃'),
    0xAB: ('水面蒸发量 ESV', 5, 1, 'mm'),
    0xAC: ('蒲福风力等级 FB', 2, 0, '级'),

    # 水质
    0xB1: ('pH值 PH', 4, 2, ''),
    0xB2: ('溶解氧 DO', 4, 1, 'mg/L'),
    0xB3: ('化学需氧量 COD', 5, 1, 'mg/L'),
    0xB4: ('氨氮 NH3N', 5, 2, 'mg/L'),
    0xB5: ('高锰酸盐指数 CODMN', 5, 1, 'mg/L'),
    0xB6: ('总磷 TP', 5, 3, 'mg/L'),
    0xB7: ('总氮 TN', 5, 2, 'mg/L'),
    0xB8: ('浊度 TB', 5, 1, 'NTU'),
    0xB9: ('电导率 COND', 5, 1, 'μS/cm'),
    0xBA: ('叶绿素a CHL', 5, 1, 'μg/L'),
    0xBB: ('水位 Z_水质', 7, 3, 'm'),
    0xBC: ('水势 WP', 7, 3, 'm'),
}

# 要素ID列表（用于前端选择），格式: [(引导符, 要素名称, 总位数, 小数位, 单位), ...]
ELEMENT_OPTIONS = sorted(
    [(g, name, td, dp, u) for g, (name, td, dp, u) in ELEMENT_BY_GUIDE.items()],
    key=lambda x: x[0]
)


# ===================== 工具函数 =====================

def _crc16(data: bytes) -> int:
    """
    CRC16 校验，生成多项式: X^16 + X^15 + X^2 + 1
    与标准 CRC-16-IBM (Modbus) 一致
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def _crc16_bytes(data: bytes) -> bytes:
    """返回 CRC16 校验结果的2字节（高位在前，低位在后）"""
    crc = _crc16(data)
    return bytes([(crc >> 8) & 0xFF, crc & 0xFF])


def _int_to_bcd(value: int, byte_count: int) -> bytes:
    """
    将整数值转为 BCD 编码（每个字节编码2个十进制数字）
    value: 整数值（不含小数点）
    byte_count: 输出的字节数
    
    示例: _int_to_bcd(125, 3) -> b'\x00\x01\x25' (即 0x00 0x01 0x25)
    """
    result = bytearray(byte_count)
    for i in range(byte_count - 1, -1, -1):
        result[i] = (value % 10) | ((value // 10 % 10) << 4)
        value //= 100
    return bytes(result)


def _bcd_str_to_bytes(bcd_str: str, byte_count: int) -> bytes:
    """
    将 BCD 字符串（每个字符一个十进制数字）转为 BCD 字节
    bcd_str: BCD数字字符串，如 "00125"
    byte_count: 输出字节数
    
    示例: _bcd_str_to_bytes("00125", 3) -> b'\x00\x12\x50'
    """
    # 左侧补零到所需长度
    total_digits = byte_count * 2
    bcd_str = bcd_str.zfill(total_digits)
    result = bytearray(byte_count)
    for i in range(byte_count):
        high_nibble = int(bcd_str[i * 2]) if i * 2 < len(bcd_str) else 0
        low_nibble = int(bcd_str[i * 2 + 1]) if i * 2 + 1 < len(bcd_str) else 0
        result[i] = (high_nibble << 4) | low_nibble
    return bytes(result)


def _encode_data_def(total_digits: int, decimal_places: int = 0) -> int:
    """
    编码数据定义字节
    格式: (数据字节数 << 3) | 小数位数
    
    验证示例（PDF文档）:
    - 雨量 N(5,1): byte_count=3, def = (3<<3)|1 = 25 = 0x19
    - 水位 N(7,3): byte_count=4, def = (4<<3)|3 = 35 = 0x23
    - 电压 N(4,2): byte_count=2, def = (2<<3)|2 = 18 = 0x12
    """
    byte_count = (total_digits + 1) // 2  # 向上取整
    return (byte_count << 3) | (decimal_places & 0x07)


def _encode_numeric(value: float, total_digits: int, decimal_places: int) -> bytes:
    """
    将浮点数按 N(total_digits, decimal_places) 格式编码为 BCD 字节
    
    value: 浮点数值
    total_digits: 除小数点外的总位数
    decimal_places: 小数位数
    
    示例: _encode_numeric(12.5, 5, 1) -> 12.5 -> "00125" -> b'\x00\x12\x50'
    """
    # 将数值转为整数（乘以10^decimal_places）
    scaled = int(round(value * (10 ** decimal_places)))
    
    # 转为字符串并左侧补零
    str_val = str(scaled).zfill(total_digits)
    
    # 取最后 total_digits 位（防止溢出）
    if len(str_val) > total_digits:
        str_val = str_val[-total_digits:]
    
    byte_count = (total_digits + 1) // 2
    return _bcd_str_to_bytes(str_val, byte_count)


# ===================== 报文构建 =====================

def build_message(
    center_addr: int,
    station_addr: bytes,
    password: int,
    func_code: int,
    body: bytes,
    mode: str = 'M1'
) -> bytes:
    """
    构建完整的 SL651-2014 HEX/BCD 上行报文帧
    
    参数:
        center_addr: 中心站地址 (1-255)
        station_addr: 遥测站地址 (5 bytes)
        password: 密码 (2 bytes HEX)
        func_code: 功能码 (1 byte)
        body: 报文正文
        mode: 传输模式, M1(发送/无回答) 或 M2(发送/确认)
    
    返回: 完整报文 bytes
    """
    # 报文起始符: 7E7EH
    header = FRAME_START_HEX
    
    # 报头: 中心站地址(1B) + 遥测站地址(5B) + 密码(2B) + 功能码(1B)
    header += bytes([center_addr & 0xFF])
    header += station_addr[:5]
    header += struct.pack('>H', password & 0xFFFF)
    header += bytes([func_code & 0xFF])
    
    # 报文上行标识及长度 (2B HEX)
    # 高4位: 0000=上行, 1000=下行
    # 低12位: 报文正文长度 (STX之后, ETX/ETB之前的字节数)
    body_len = len(body)
    if body_len > 4095:
        raise ValueError(f"报文正文过长: {body_len} > 4095")
    length_flag = body_len & 0x0FFF  # 上行标识 0xxx (高4位=0)
    header += struct.pack('>H', length_flag)
    
    # 报文起始符: STX
    header += STX
    
    # 报文结束符
    if mode == 'M1':
        end_char = ETX
    else:
        end_char = ETB
    
    # 计算CRC校验（校验码前所有字节）
    data_for_crc = header + body + end_char
    crc = _crc16_bytes(data_for_crc)
    
    return header + body + end_char + crc


def build_timed_report_body(
    serial_no: int,
    report_time: datetime,
    station_addr: bytes,
    station_type: int,
    obs_time: datetime,
    elements_data: list,      # [(guide_byte, value, total_digits, decimal_places), ...]
    voltage: float = 12.50,
) -> bytes:
    """
    构建定时报（功能码32H）报文正文
    
    参数:
        serial_no: 流水号 (1-65535)
        report_time: 发报时间
        station_addr: 遥测站地址 (5 bytes)
        station_type: 遥测站分类码 (1 byte HEX)
        obs_time: 观测时间
        elements_data: 要素数据列表 [(引导符, 值, 总位数, 小数位数), ...]
        voltage: 电源电压 (V)
    
    返回: 报文正文 bytes
    """
    body = bytearray()
    
    # 1. 流水号 (2B HEX)
    body += struct.pack('>H', serial_no & 0xFFFF)
    
    # 2. 发报时间 (6B BCD, YYMMDDHHmmSS)
    time_bcd = _int_to_bcd(
        int(report_time.strftime('%y%m%d%H%M%S')), 6
    )
    body += time_bcd
    
    # 3. 地址标识符 (F1 F1H) + 遥测站地址 (5B)
    body.append(GUIDE_STATION_ADDR)
    body.append(GUIDE_STATION_ADDR)
    body += station_addr[:5]
    
    # 4. 遥测站分类码 (1B)
    body.append(station_type & 0xFF)
    
    # 5. 观测时间标识符 (F0 F0H) + 观测时间 (5B BCD, YYMMDDHHmm)
    body.append(GUIDE_OBS_TIME)
    body.append(GUIDE_OBS_TIME)
    obs_bcd = _int_to_bcd(
        int(obs_time.strftime('%y%m%d%H%M')), 5
    )
    body += obs_bcd
    
    # 6. 要素信息组
    for guide, value, total_digits, decimal_places in elements_data:
        if value is None:
            continue
        body.append(guide & 0xFF)
        # 数据定义 (byte_count << 3) | decimal_places
        body.append(_encode_data_def(total_digits, decimal_places))
        # 数据值
        body += _encode_numeric(value, total_digits, decimal_places)
    
    # 7. 电压要素 (标识符38H + N(4,2)) - 如果未在自定义要素中指定
    has_voltage = any(g == GUIDE_VOLTAGE for g, *_ in elements_data)
    if voltage is not None and not has_voltage:
        body.append(GUIDE_VOLTAGE)
        body.append(_encode_data_def(4, 2))
        body += _encode_numeric(voltage, 4, 2)
    elif voltage is not None and has_voltage:
        # 电压已通过要素列表提供，使用列表中的电压值
        pass
    
    return bytes(body)


def decode_message(data: bytes) -> dict:
    """解析 SL651-2014 HEX/BCD 报文（用于调试/验证）"""
    if len(data) < 16:
        return {'error': '报文太短'}
    
    result = {}
    offset = 0
    
    # 帧起始符
    if data[offset:offset+2] != FRAME_START_HEX:
        return {'error': '帧起始符无效'}
    result['frame_start'] = '7E7E'
    offset += 2
    
    # 报头
    result['center_addr'] = data[offset]
    offset += 1
    
    result['station_addr'] = data[offset:offset+5].hex().upper()
    offset += 5
    
    result['password'] = f"{struct.unpack('>H', data[offset:offset+2])[0]:04X}"
    offset += 2
    
    result['func_code'] = f"{data[offset]:02X}H"
    offset += 1
    
    # 报文长度标志
    length_flag = struct.unpack('>H', data[offset:offset+2])[0]
    result['is_uplink'] = (length_flag & 0x8000) == 0
    result['body_length'] = length_flag & 0x0FFF
    offset += 2
    
    # 报文起始符
    result['body_start'] = f"{data[offset]:02X}H"
    offset += 1
    
    # 正文
    body_len = result['body_length']
    result['body'] = data[offset:offset+body_len].hex().upper()
    offset += body_len
    
    # 结束符
    result['end_char'] = f"{data[offset]:02X}H"
    offset += 1
    
    # CRC
    result['crc'] = data[offset:offset+2].hex().upper()
    
    # 验证CRC
    data_for_crc = data[:offset]
    calc_crc = _crc16(data_for_crc)
    actual_crc = struct.unpack('>H', data[offset:offset+2])[0]
    result['crc_valid'] = (calc_crc == actual_crc)
    
    return result


if __name__ == '__main__':
    # 简单测试
    test_station = bytes([0x00, 0x12, 0x34, 0x56, 0x78])
    
    body = build_timed_report_body(
        serial_no=1,
        report_time=datetime(2025, 7, 25, 12, 0, 0),
        station_addr=test_station,
        station_type=STATION_TYPES['河道'],
        obs_time=datetime(2025, 7, 25, 12, 0),
        elements_data=[
            (GUIDE_PN05, 2.5, 5, 1),     # 5分钟时降水量 2.5mm
            (GUIDE_Z, 150.325, 7, 3),    # 河道水位 150.325m
        ],
        voltage=12.50,
    )
    
    msg = build_message(
        center_addr=1,
        station_addr=test_station,
        password=0x1234,
        func_code=FUNC_TIMED,
        body=body,
        mode='M1',
    )
    
    print(f"报文长度: {len(msg)} bytes")
    print(f"报文HEX: {msg.hex().upper()}")
    
    decoded = decode_message(msg)
    import json
    print(json.dumps(decoded, indent=2, ensure_ascii=False))
