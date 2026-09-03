"""
SL651-2014 水文监测数据通信规约 - 数据模拟上传工具 Web 后端
"""

import sys
import os
import socket
import json
import re
import webbrowser
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, request, jsonify

# PyInstaller 打包后，模板路径在 sys._MEIPASS 临时目录中
if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    app = Flask(__name__, template_folder=template_folder)
else:
    app = Flask(__name__)

from sl651_protocol import (
    build_message, build_timed_report_body,
    ELEMENT_DEFS, ELEMENT_REFS, ELEMENT_BY_GUIDE, ELEMENT_OPTIONS,
    STATION_TYPES, FUNC_TIMED, decode_message,
    GUIDE_PN, GUIDE_PN05, GUIDE_PN10, GUIDE_PS, GUIDE_PT,
    GUIDE_Z, GUIDE_ZU, GUIDE_VOLTAGE,
    GUIDE_FLOW, GUIDE_TA, GUIDE_WS,
    _encode_data_def, _encode_numeric, _int_to_bcd,
)


def parse_station_addr(addr_str: str) -> bytes:
    """
    解析遥测站地址
    支持格式:
      - 纯HEX: "0x0012345678" 或 "0012345678"
      - 斜杠分隔: "44/01/0001" (行政区划/类型/编号)
      - BCD: "bcd:4401000001"
    """
    addr_str = addr_str.strip()
    if addr_str.lower().startswith('0x'):
        hex_str = addr_str[2:]
    elif addr_str.lower().startswith('bcd:'):
        # BCD格式: "bcd:4401000001" -> 10位BCD数字转为5字节
        bcd_str = addr_str[4:].zfill(10)
        result = bytearray(5)
        for i in range(5):
            h = int(bcd_str[i * 2])
            l = int(bcd_str[i * 2 + 1])
            result[i] = (h << 4) | l
        return bytes(result)
    elif '/' in addr_str:
        # 斜杠分隔: "44/01/0001" -> 按行政区划码编码
        # A5,A4,A3: BCD 行政区划码(6位), A2,A1: HEX 编号
        parts = addr_str.split('/')
        if len(parts) == 3:
            region = parts[0].zfill(6)  # 6位行政区划码
            stype = parts[1]            # 站类型
            number = parts[2]           # 站编号
            # 组合成常规格式
            hex_str = region + stype + number.zfill(4)
        else:
            hex_str = addr_str.replace('/', '').zfill(10)
    else:
        hex_str = addr_str.zfill(10)
    
    # 将HEX字符串转为5字节（每2位HEX=1字节）
    hex_str = hex_str[-10:]  # 取后10位
    return bytes.fromhex(hex_str.zfill(10))


def parse_password(pwd_str: str) -> int:
    """解析密码字符串为整数"""
    pwd_str = pwd_str.strip()
    if pwd_str.lower().startswith('0x'):
        return int(pwd_str, 16)
    try:
        return int(pwd_str)
    except ValueError:
        return int(pwd_str, 16) if all(c in '0123456789ABCDEFabcdef' for c in pwd_str) else 0x1234


def is_valid_ip(addr: str) -> bool:
    """检查是否为有效IP地址"""
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, addr):
        return False
    return all(0 <= int(p) <= 255 for p in addr.split('.'))


def is_valid_port(port: int) -> bool:
    """检查端口号是否有效"""
    return 1 <= port <= 65535


def get_config_path():
    """配置文件路径：打包后放在EXE同级目录，开发时放在项目目录"""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'config.json')

def parse_hex_guide(val) -> int:
    """健壮解析引导符十六进制值。始终按HEX解析，返回0表示无效。"""
    if val is None:
        return 0
    if isinstance(val, bool):
        return 0
    if isinstance(val, (int, float)):
        v = int(val)
        return v if 0 < v <= 0xFF else 0
    s = str(val).strip()
    if not s:
        return 0
    if len(s) >= 2 and (s[:2] == '0x' or s[:2] == '0X'):
        s = s[2:]
    if s and s[-1].lower() == 'h':
        s = s[:-1]
    s = s.strip()
    if not s:
        return 0
    try:
        v = int(s, 16)
        return v if 0 < v <= 0xFF else 0
    except (ValueError, TypeError):
        return 0


def build_elements_from_custom(custom_elements) -> tuple:
    """将前端自定义要素转为 (elements列表, parsed详情列表) 二元组"""
    import json as _json
    elements = []
    parsed = []
    if isinstance(custom_elements, str):
        try:
            custom_elements = _json.loads(custom_elements)
        except _json.JSONDecodeError:
            custom_elements = []
    if not isinstance(custom_elements, list):
        return elements, parsed
    for ce in custom_elements:
        # 支持两种格式:
        # 1. 标准要素模式: {element_id: int, value: float} (前端 quickAdd)
        # 2. 自定义要素模式: {guide: str, total_digits, decimal_places, value}
        element_id = ce.get('element_id')
        if element_id is not None:
            guide = int(element_id)
            elem_info = ELEMENT_BY_GUIDE.get(guide) if guide in ELEMENT_BY_GUIDE else None
            if not elem_info:
                continue
            try:
                # ELEMENT_BY_GUIDE 值为元组: (name, total_digits, decimal_places, unit)
                total_digits = elem_info[1]
                decimal_places = elem_info[2]
                value = float(ce.get('value', 0))
            except (ValueError, TypeError):
                value = None
        else:
            guide = parse_hex_guide(ce.get('guide'))
            if guide == 0:
                continue
            try:
                total_digits = int(ce.get('total_digits', 5))
                decimal_places = int(ce.get('decimal_places', 1))
                value = float(ce.get('value', 0))
            except (ValueError, TypeError):
                value = None

        elements.append((guide, value, total_digits, decimal_places))
        parsed.append({
            'guide': f'0x{guide:02X}',
            'guide_dec': guide,
            'total_digits': total_digits,
            'decimal_places': decimal_places,
            'value': value,
        })
    return elements, parsed



# ===================== API 路由 =====================

def _test_single_target(transport, target, port):
    """测试单个目标连接，返回 (success, status, message, target_ip)"""
    if not target:
        return (False, 'disconnected', '请输入目标地址', None)
    if not is_valid_port(port):
        return (False, 'disconnected', '端口号无效', None)
    
    if not is_valid_ip(target):
        try:
            target_ip = socket.gethostbyname(target)
        except socket.gaierror as e:
            return (False, 'disconnected', f'域名解析失败: {str(e)}', None)
    else:
        target_ip = target
    
    if transport == 'tcp':
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((target_ip, port))
            sock.close()
            return (True, 'connected', f'TCP连接成功: {target_ip}:{port}', target_ip)
        except socket.timeout:
            return (False, 'timeout', f'TCP连接超时: {target_ip}:{port}', target_ip)
        except ConnectionRefusedError:
            return (False, 'refused', f'TCP连接被拒绝: {target_ip}:{port}', target_ip)
        except Exception as e:
            return (False, 'disconnected', f'TCP连接失败: {str(e)}', target_ip)
    else:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2)
            sock.connect((target_ip, port))
            sock.close()
            return (True, 'connected', f'UDP目标可达: {target_ip}:{port}', target_ip)
        except Exception as e:
            return (False, 'disconnected', f'UDP连接失败: {str(e)}', target_ip)


@app.route('/api/test_connection', methods=['POST'])
def test_connection():
    """测试目标连接状态（支持单目标或多目标）"""
    try:
        data = request.get_json()
        
        # 兼容旧版单目标格式
        if 'target' in data:
            targets = [{
                'transport': data.get('transport', 'tcp').lower(),
                'target': data.get('target', '').strip(),
                'port': int(data.get('port', 5001)),
            }]
        else:
            targets = data.get('targets', [])
            if not targets:
                return jsonify({'success': False, 'error': '未提供连接目标'}), 400
        
        results = []
        for i, t in enumerate(targets):
            transport = t.get('transport', 'tcp').lower()
            target = t.get('target', '').strip()
            port = int(t.get('port', 5001))
            
            ok, status, msg, tip = _test_single_target(transport, target, port)
            results.append({
                'index': i + 1,
                'success': ok,
                'status': status,
                'message': msg,
                'target_ip': tip,
                'transport': transport,
                'target': target,
                'port': port,
            })
        
        all_ok = all(r['success'] for r in results)
        return jsonify({
            'success': all_ok,
            'results': results,
        })
                
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/')
def index():
    """主页面"""
    return render_template('index.html',
        station_types=STATION_TYPES.keys(),
        element_defs=ELEMENT_DEFS,
        element_refs=ELEMENT_REFS,
        element_options=ELEMENT_OPTIONS,
    )


@app.route('/api/upload', methods=['POST'])
def upload_data():
    """
    上传数据接口（支持多目标并发发送）
    
    请求参数:
        targets: [{
            transport: 'tcp'|'udp',
            target: IP或域名,
            port: 端口号,
            enabled: true/false
        }, ...]
        center_addr: 中心站地址 (1-255)
        station_addr: 遥测站地址字符串
        password: 测站密码 (1-65535)
        station_type: 遥测站分类码名称
        report_time: 发报时间, ISO格式
        obs_time: 观测时间, ISO格式
        serial_no: 流水号 (1-65535)
        voltage: 电源电压 (V)
        count: 发送次数 (1-100)
    """
    try:
        data = request.get_json()
        
        # ===== 解析多目标 =====
        targets_raw = data.get('targets', [])
        if not targets_raw:
            # 兼容旧版单目标格式
            targets_raw = [{
                'transport': data.get('transport', 'tcp').lower(),
                'target': data.get('target', '').strip(),
                'port': int(data.get('port', 5001)),
                'enabled': True,
            }]
        
        enabled_targets = []
        for t in targets_raw:
            if t.get('enabled', True):
                transport = t.get('transport', 'tcp').lower()
                target = t.get('target', '').strip()
                port = int(t.get('port', 5001))
                if target and port:
                    enabled_targets.append({
                        'transport': transport,
                        'target': target,
                        'port': port,
                    })
        
        if not enabled_targets:
            return jsonify({'success': False, 'error': '请至少启用并配置一个连接目标'}), 400
        
        # ===== 解析通用参数 =====
        center_addr = int(data.get('center_addr', 1))
        pwd_raw = data.get('password', '0x1234')
        password = parse_password(pwd_raw)
        station_type_name = data.get('station_type', '河道')
        serial_no = int(data.get('serial_no', 1))
        count = int(data.get('count', 1))
        voltage = float(data.get('voltage', 12.50))
        
        report_time_str = data.get('report_time', datetime.now().isoformat())
        obs_time_str = data.get('obs_time', datetime.now().isoformat())
        
        try:
            report_time = datetime.fromisoformat(report_time_str)
        except ValueError:
            return jsonify({'success': False, 'error': '发报时间格式无效'}), 400
        
        try:
            obs_time = datetime.fromisoformat(obs_time_str)
        except ValueError:
            obs_time = report_time.replace(second=0)
        
        station_addr_raw = data.get('station_addr', '').strip()
        # 多测站地址支持
        station_addrs_raw = data.get('station_addrs', [])
        if not station_addrs_raw:
            # 兼容旧版单地址
            if station_addr_raw:
                station_addrs_raw = [station_addr_raw]
        
        if not station_addrs_raw:
            return jsonify({'success': False, 'error': '请至少提供一个测站地址'}), 400
        
        # 解析所有测站地址
        station_addrs_parsed = []
        for addr_str in station_addrs_raw:
            station_addrs_parsed.append({
                'raw': addr_str,
                'bytes': parse_station_addr(addr_str),
            })
        
        station_type = STATION_TYPES.get(station_type_name, STATION_TYPES['河道'])
        
        elements, elements_parsed = build_elements_from_custom(data.get('custom_elements', []))
        
        if not elements:
            return jsonify({'success': False, 'error': '至少需要添加一个要素'}), 400
        
        if not (1 <= center_addr <= 255):
            return jsonify({'success': False, 'error': '中心站地址必须在1-255之间'}), 400
        if not (1 <= serial_no <= 65535):
            return jsonify({'success': False, 'error': '流水号必须在1-65535之间'}), 400
        if not (1 <= count <= 100):
            return jsonify({'success': False, 'error': '发送次数必须在1-100之间'}), 400
        
        # ===== 构建报文（每个测站生成一份） =====
        first_station_addr = station_addrs_parsed[0]['bytes']
        first_station_raw = station_addrs_parsed[0]['raw']
        first_msg = None
        
        # 为第一个测站生成预览用报文
        body = build_timed_report_body(
            serial_no=serial_no,
            report_time=report_time,
            station_addr=first_station_addr,
            station_type=station_type,
            obs_time=obs_time,
            elements_data=elements,
            voltage=voltage,
        )
        
        first_msg = build_message(
            center_addr=center_addr,
            station_addr=first_station_addr,
            password=password,
            func_code=FUNC_TIMED,
            body=body,
            mode='M1',
        )
        
        # ===== 预解析域名 =====
        resolved_targets = []
        for t in enabled_targets:
            target = t['target']
            if not is_valid_ip(target):
                try:
                    tip = socket.gethostbyname(target)
                except socket.gaierror as e:
                    return jsonify({
                        'success': False,
                        'error': f'域名解析失败 [{target}]: {str(e)}'
                    }), 400
            else:
                tip = target
            resolved_targets.append({
                **t,
                'target_ip': tip,
            })
        
        # ===== 向所有测站×目标发送 =====
        def send_one_message(transport, target_ip, target, port, message_bytes, serial):
            """发送单条报文到单个目标"""
            try:
                if transport == 'tcp':
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(10)
                    sock.connect((target_ip, port))
                    sock.sendall(message_bytes)
                    sock.close()
                else:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.settimeout(5)
                    sock.sendto(message_bytes, (target_ip, port))
                    sock.close()
                return {'index': serial, 'status': 'success', 'serial_no': serial}
            except Exception as e:
                return {'index': serial, 'status': 'error', 'error': str(e), 'serial_no': serial}
        
        def build_msg_for_station(sta_bytes, sta_raw, sta_serial):
            """为一个测站构建多份报文（count>1时）"""
            msgs = []
            for i in range(count):
                current_serial = (sta_serial + i) & 0xFFFF
                if count > 1:
                    b = build_timed_report_body(
                        serial_no=current_serial,
                        report_time=report_time,
                        station_addr=sta_bytes,
                        station_type=station_type,
                        obs_time=obs_time,
                        elements_data=elements,
                        voltage=voltage,
                    )
                    m = build_message(
                        center_addr=center_addr,
                        station_addr=sta_bytes,
                        password=password,
                        func_code=FUNC_TIMED,
                        body=b,
                        mode='M1',
                    )
                else:
                    b = build_timed_report_body(
                        serial_no=current_serial,
                        report_time=report_time,
                        station_addr=sta_bytes,
                        station_type=station_type,
                        obs_time=obs_time,
                        elements_data=elements,
                        voltage=voltage,
                    )
                    m = build_message(
                        center_addr=center_addr,
                        station_addr=sta_bytes,
                        password=password,
                        func_code=FUNC_TIMED,
                        body=b,
                        mode='M1',
                    )
                msgs.append((m, current_serial))
            return msgs
        
        # 收集所有发送任务: (message_bytes, serial, target_info, station_addr)
        all_tasks = []
        for sta_idx, sta_info in enumerate(station_addrs_parsed):
            sta_msgs = build_msg_for_station(sta_info['bytes'], sta_info['raw'], serial_no + sta_idx * count)
            for mi, (msg_bytes, msg_serial) in enumerate(sta_msgs):
                for ti in resolved_targets:
                    all_tasks.append((msg_bytes, msg_serial, ti, sta_info['raw']))
        
        # 线程池并发发送
        stations_sent_map = {}  # sta_addr -> targets_sent
        
        def send_task(task):
            msg_bytes, msg_serial, tinfo, sta_addr = task
            result = send_one_message(
                tinfo['transport'], tinfo['target_ip'], tinfo['target'],
                tinfo['port'], msg_bytes, msg_serial
            )
            return (sta_addr, msg_serial, tinfo, result)
        
        with ThreadPoolExecutor(max_workers=min(len(all_tasks), 16)) as executor:
            futures = [executor.submit(send_task, t) for t in all_tasks]
            for future in as_completed(futures):
                sta_addr, msg_serial, tinfo, result = future.result()
                if sta_addr not in stations_sent_map:
                    stations_sent_map[sta_addr] = {}
                if tinfo['target'] not in stations_sent_map[sta_addr]:
                    stations_sent_map[sta_addr][tinfo['target']] = {
                        'transport': tinfo['transport'],
                        'target': tinfo['target'],
                        'target_ip': tinfo['target_ip'],
                        'port': tinfo['port'],
                        'send_results': [],
                    }
                stations_sent_map[sta_addr][tinfo['target']]['send_results'].append(result)
        
        # 构建返回结构
        stations_sent = []
        for sta_idx, sta_info in enumerate(station_addrs_parsed):
            sta_raw = sta_info['raw']
            targets_list = []
            if sta_raw in stations_sent_map:
                for tname, tdata in stations_sent_map[sta_raw].items():
                    targets_list.append(tdata)
            stations_sent.append({
                'station_addr': sta_raw,
                'serial_no': serial_no + sta_idx * count,
                'targets_sent': targets_list,
            })
        
        # ===== 统计 =====
        total_success = 0
        total_count = 0
        for stn in stations_sent:
            for ts in stn['targets_sent']:
                for sr in ts['send_results']:
                    total_count += 1
                    if sr['status'] == 'success':
                        total_success += 1
        
        first_target = resolved_targets[0] if resolved_targets else None
        
        return jsonify({
            'success': total_success > 0,
            'message_hex': first_msg.hex().upper(),
            'message_length': len(first_msg),
            'station_addr': first_station_raw,
            'station_count': len(station_addrs_parsed),
            'report_time': report_time.strftime('%Y-%m-%d %H:%M:%S'),
            'obs_time': obs_time.strftime('%Y-%m-%d %H:%M'),
            'decoded': decode_message(first_msg),
            'elements_used': elements_parsed,
            'total_success': total_success,
            'total_count': total_count,
            'stations_sent': stations_sent,
        })
        
    except ValueError as e:
        return jsonify({'success': False, 'error': f'参数格式错误: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'未知错误: {str(e)}'}), 500


@app.route('/api/preview', methods=['POST'])
def preview_message():
    """预览生成的报文（不发送）"""
    try:
        data = request.get_json()
        
        center_addr = int(data.get('center_addr', 1))
        pwd_raw = data.get('password', '0x1234')
        password = parse_password(pwd_raw)
        station_type_name = data.get('station_type', '河道')
        serial_no = int(data.get('serial_no', 1))
        voltage = float(data.get('voltage', 12.50))
        
        report_time = datetime.fromisoformat(data.get('report_time', datetime.now().isoformat()))
        obs_time = datetime.fromisoformat(data.get('obs_time', datetime.now().isoformat()))
        
        station_addr_raw = data.get('station_addr', '').strip()
        # 多测站地址支持
        station_addrs_raw = data.get('station_addrs', [])
        if not station_addrs_raw:
            if station_addr_raw:
                station_addrs_raw = [station_addr_raw]
        
        if not station_addrs_raw:
            return jsonify({'success': False, 'error': '请至少提供一个测站地址'}), 400
        
        # 用第一个测站地址预览
        first_station_raw = station_addrs_raw[0]
        station_addr = parse_station_addr(first_station_raw)
        station_type = STATION_TYPES.get(station_type_name, STATION_TYPES['河道'])
        
        elements, elements_parsed = build_elements_from_custom(data.get('custom_elements', []))
        
        if not elements:
            return jsonify({'success': False, 'error': '至少需要添加一个自定义要素'}), 400
        
        body = build_timed_report_body(
            serial_no=serial_no,
            report_time=report_time,
            station_addr=station_addr,
            station_type=station_type,
            obs_time=obs_time,
            elements_data=elements,
            voltage=voltage,
        )
        
        msg = build_message(
            center_addr=center_addr,
            station_addr=station_addr,
            password=password,
            func_code=FUNC_TIMED,
            body=body,
            mode='M1',
        )
        
        decoded = decode_message(msg)
        
        return jsonify({
            'success': True,
            'message_hex': msg.hex().upper(),
            'message_length': len(msg),
            'report_time': report_time.strftime('%Y-%m-%d %H:%M:%S'),
            'obs_time': obs_time.strftime('%Y-%m-%d %H:%M'),
            'body_hex': body.hex().upper(),
            'body_length': len(body),
            'decoded': decoded,
            'elements_used': elements_parsed,
            'station_addr': first_station_raw,
            'station_addrs': station_addrs_raw,
            'station_count': len(station_addrs_raw),
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/config', methods=['GET'])
def load_config():
    """读取本地保存的页面配置"""
    path = get_config_path()
    if not os.path.exists(path):
        return jsonify({})
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify({})


@app.route('/api/config', methods=['POST'])
def save_config():
    """保存页面配置到本地，重启后自动恢复"""
    data = request.get_json(silent=True) or {}
    try:
        path = get_config_path()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 50)
    print("  SL651 水文监测数据模拟上传工具")
    print("  访问地址: http://127.0.0.1:5000")
    print("=" * 50)
    # 自动打开浏览器
    webbrowser.open('http://127.0.0.1:5000')
    app.run(host='0.0.0.0', port=5000, debug=False)
