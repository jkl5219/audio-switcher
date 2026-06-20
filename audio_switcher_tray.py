#!/usr/bin/env python3
# audio_switcher_tray.py - 小钻风音频切换器 v5.29
# 架构: 主线程跑 Tkinter GUI, 托盘用 Windows 原生 Shell_NotifyIconW API
#   1. _switching 互斥锁防并发双击：快速双击只执行一次切换，防止 COM 踩踏卡死
#   2. 去除 _switch_selected 中 get_device_name_map() 冗余 COM 查询（UI 层已拼好名称）
#   3. _try_switch() 统一入口，按钮和双击都走互斥保护

import ctypes
import json
import logging
import os
import sys
import threading
import time
import webbrowser
import winreg
import winsound
from ctypes import wintypes
from pathlib import Path

# =============================================================================
# 常量
# =============================================================================

APP_NAME = '小钻风音频切换器'
APP_NAME_EN = 'XiaoZuanFeng Audio Switcher'
APP_VER  = 'v1.0'
APP_AUTHOR = '这是啥呀'
APP_CONTACT = '18023717@qq.com'
GITHUB_URL = 'https://github.com/jkl5219/audio-switcher'
AFDIAN_URL = 'https://afdian.com/a/jkl5219'
MUTEX_NAME = 'Global\\XiaoZuanFengAudioMutex_v6'

APP_DIR  = Path(os.environ.get('APPDATA', '.')) / '小钻风音频切换器'
_old_app_dir = Path(os.environ.get('APPDATA', '.')) / '小智音频切换'
if not APP_DIR.exists() and _old_app_dir.exists():
    import shutil
    try:
        shutil.copytree(_old_app_dir, APP_DIR)
    except Exception:
        pass
APP_DIR.mkdir(parents=True, exist_ok=True)
CFG_FILE = APP_DIR / 'audio_switcher_settings.json'
LOG_FILE = APP_DIR / 'app.log'

def _icon_path():
    base = Path(getattr(sys, '_MEIPASS', Path(os.path.dirname(os.path.abspath(__file__)))))
    return base / 'icon.ico'

def _is_frozen():
    """是否为 PyInstaller 打包的 EXE。"""
    return getattr(sys, 'frozen', False)

DEFAULT_CFG = {
    'auto_start': False,
    'notify': True,
    'hotkeys': {},
    'hotkey_cycle': '',
    'hotkey_mute': '',
    'device_aliases': {},
    'device_volumes': {},
    'device_preset_slots': {},
    'language': 'auto',     # auto | zh | en
}

# =============================================================================
# 多语言 — V5.0
# =============================================================================

_LANG_STRINGS = {
    'zh': {
        'app_title': '小钻风音频切换器',
        'current_device': '当前设备',
        'audio_devices': '音频输出设备',
        'device_hint': '单击选中, 双击直接切换  |  拖动滑条调节音量(自动记忆)',
        'no_devices': '未检测到音频设备',
        'current_tag': '[当前]',
        'refresh': '刷新',
        'test_sound': '测试声音',
        'switch_to': '切换到该设备',
        'global_hotkeys': '全局热键',
        'hotkey_hint': '点击输入框, 然后按下快捷键组合 (支持 Win 键, 修改后自动保存)',
        'cycle_switch': '循环切换:',
        'cycle_desc': '在全部设备间循环',
        'mute_toggle': '静音切换:',
        'mute_desc': '切换当前设备静音',
        'muted': '已静音',
        'unmuted': '已取消静音',
        'device_hotkeys': '设备专属热键',
        'auto_start': '开机自动启动',
        'show_notify': '切换后显示通知',
        'lang_label': '语言:',
        'minimize_tray': '最小化到托盘',
        'exit': '退出',
        'saved': '✓ 已保存',
        'switched_to': '已切换',
        'switch_failed': '切换失败',
        'cannot_switch': '无法切换到',
                'cycle_switched': '循环切换',
        'set_preset_val': '设置预设音量值',
        'custom_preset': '自定义预设',
        'preset_slot': '预设档位',
        'low': '低',
        'mid': '中',
        'high': '高',
        'preset_applied': '预设音量已应用',
        'device_not_ready': '设备未就绪，可能未连接蓝牙',
        'switch_verify_failed': '切换未生效，请检查设备连接',
        'open_bt_settings': '打开蓝牙设置',
        'select_first': '请先点击选择一个设备',
        'click_to_set': '点击设置',
        'recording_hint': '按下快捷键... (ESC取消)',
        'need_modifier': '需要 Ctrl/Alt/Shift/Win 组合',
        'press_keys': '按下快捷键...',
        'switch_device': '切换到指定设备',
        'no_device_switch': '切换到指定设备 (无设备)',
        'show_main': '显示主界面',
        'device_alias': '设备别名',
        'alias_hint': '单击设备名编辑别名',
        'set_alias': '设置别名',
        'clear_alias': '清除别名',
        'alias_prompt': '请输入设备别名:',
        'restore_original': '还原原生名字',
        'ok': '确定',
        'cancel': '取消',
        'device_name': '原始名称',
        'already_running': '程序已在运行中, 但无法定位窗口。\n\n请检查系统托盘 (右下角) 是否有图标,\n或按 Ctrl+Shift+Esc 打开任务管理器结束进程后重启。',
        'fatal_error': '程序发生致命错误',
        'log_file': '日志文件',
        'no_alias': '(未设置别名)',
        'about': '关于',
        'help': '帮助',
        'help_switch': '切换设备',
        'help_alias': '设备别名',
        'help_volume': '音量调节',
        'help_preset': '预设音量',
        'help_hotkey': '全局热键',
        'help_autostart': '开机自启',
        'help_tray': '系统托盘',
        'help_switch_desc': '双击设备名或设备行任意位置即可切换',
        'help_alias_desc': '单击设备名旁的 ✎ 图标，输入别名后确认',
        'help_volume_desc': '拖动滑块调整音量（自动记忆每个设备）',
        'help_preset_desc': '单击预设按钮应用，双击可编辑预设值',
        'help_hotkey_desc': '在设置中配置设备切换快捷键组合',
        'help_autostart_desc': '在设置中勾选开机自动启动复选框',
        'help_tray_desc': '右键系统托盘图标查看更多选项',
        'donate': '❤ 支持开发者',
        'feedback': '反馈问题',
        'feedback_hint': '如有问题请联系作者，或发送邮件至下方邮箱',
        'email_copied': '邮箱已复制到剪贴板',
        'github': 'GitHub',
        'about_title': '关于',
        'app_info': '一款简洁高效的音频设备切换工具',
        'author_label': '作者:',
        'contact_label': '联系:',
        'version_label': '版本:',
        'donate_btn': '❤ 爱发电打赏支持',
        'close': '关闭',
        'hotkey_conflict': '以下热键注册失败（可能被其他程序占用）:',
        'hotkey_all_failed': '⚠️ 所有热键均注册失败！热键功能将完全不起作用。请检查是否有其他程序（如 QQ、微信、游戏）占用了这些快捷键。',
    },
    'en': {
        'app_title': 'XiaoZuanFeng Audio Switcher',
        'current_device': 'Current Device',
        'audio_devices': 'Audio Output Devices',
        'device_hint': 'Click to select, double-click to switch  |  Drag slider to adjust volume (auto-save)',
        'no_devices': 'No audio devices detected',
        'current_tag': '[Current]',
        'refresh': 'Refresh',
        'test_sound': 'Test Sound',
        'switch_to': 'Switch to This Device',
        'global_hotkeys': 'Global Hotkeys',
        'hotkey_hint': 'Click input box, then press key combo (supports Win key, auto-save on change)',
        'cycle_switch': 'Cycle Switch:',
        'cycle_desc': 'Cycle through all devices',
        'mute_toggle': 'Mute Toggle:',
        'mute_desc': 'Toggle current device mute',
        'muted': 'Muted',
        'unmuted': 'Unmuted',
        'device_hotkeys': 'Device Hotkeys',
        'auto_start': 'Start with Windows',
        'show_notify': 'Show notification on switch',
        'lang_label': 'Language:',
        'minimize_tray': 'Minimize to Tray',
        'exit': 'Exit',
        'saved': '✓ Saved',
        'switched_to': 'Switched',
        'switch_failed': 'Switch Failed',
        'cannot_switch': 'Cannot switch to',
        'cycle_switched': 'Cycle Switch',
        'low': 'Low',
        'mid': 'Mid',
        'high': 'High',
        'preset_applied': 'Preset applied',
        'device_not_ready': 'Device not ready, may be disconnected',
        'switch_verify_failed': 'Switch failed, check device connection',
        'open_bt_settings': 'Open Bluetooth Settings',
        'select_first': 'Please select a device first',
        'click_to_set': 'Click to set',
        'recording_hint': 'Press key combo... (ESC to cancel)',
        'need_modifier': 'Need Ctrl/Alt/Shift/Win combo',
        'press_keys': 'Press key combo...',
        'switch_device': 'Switch to Device',
        'no_device_switch': 'Switch to Device (No devices)',
        'show_main': 'Show Main Window',
        'device_alias': 'Device Alias',
        'alias_hint': 'Click device name to edit alias',
        'set_alias': 'Set Alias',
        'clear_alias': 'Clear Alias',
        'alias_prompt': 'Enter device alias:',
        'restore_original': 'Restore Original Name',
        'ok': 'OK',
        'cancel': 'Cancel',
        'device_name': 'Original Name',
        'already_running': 'Application is already running.\n\nCheck system tray (bottom-right) for the icon,\nor press Ctrl+Shift+Esc to open Task Manager and restart.',
        'fatal_error': 'A fatal error occurred',
        'log_file': 'Log file',
        'no_alias': '(No alias set)',
        'about': 'About',
        'help': 'Help',
        'help_switch': 'Switch Device',
        'help_alias': 'Device Alias',
        'help_volume': 'Volume Control',
        'help_preset': 'Preset Volume',
        'help_hotkey': 'Global Hotkeys',
        'help_autostart': 'Auto Start',
        'help_tray': 'System Tray',
        'help_switch_desc': 'Double-click device name or any position in the device row to switch',
        'help_alias_desc': 'Click the pencil icon next to the device name, enter an alias and confirm',
        'help_volume_desc': 'Drag the slider to adjust volume (auto-saved for each device)',
        'help_preset_desc': 'Click preset button to apply, double-click to edit preset values',
        'help_hotkey_desc': 'Configure device switch hotkey combinations in Settings',
        'help_autostart_desc': 'Check Start with Windows checkbox in Settings',
        'help_tray_desc': 'Right-click the system tray icon for more options',
        'donate': '❤ Support Developer',
        'feedback': 'Feedback',
        'feedback_hint': 'Please contact the author if you have any issues, or send an email to the address below',
        'email_copied': 'Email address copied to clipboard',
        'github': 'GitHub',
        'about_title': 'About',
        'app_info': 'A simple & efficient audio device switcher',
        'author_label': 'Author:',
        'contact_label': 'Contact:',
        'version_label': 'Version:',
        'donate_btn': '❤ Donate via Afdian',
        'close': 'Close',
        'hotkey_conflict': 'These hotkeys failed to register (may be in use by another program):',
        'hotkey_all_failed': '⚠️ All hotkeys failed to register! Hotkey functionality will be completely disabled. Please check if other programs (QQ, WeChat, games) are using these shortcuts.',
    },
}

_current_lang = 'zh'

def _detect_system_lang():
    """检测系统语言。"""
    try:
        import ctypes as _ct
        klid = _ct.windll.kernel32.GetUserDefaultUILanguage()
        # 0x0004 = zh-CN, 0x0404 = zh-TW, etc.
        if (klid & 0xFF) == 0x04:
            return 'zh'
    except Exception:
        pass
    return 'en'

def set_language(lang_code):
    """设置当前语言。"""
    global _current_lang
    if lang_code in ('auto', ''):
        _current_lang = _detect_system_lang()
    elif lang_code in _LANG_STRINGS:
        _current_lang = lang_code
    else:
        _current_lang = 'zh'

def i18n(key):
    """获取当前语言的字符串。"""
    return _LANG_STRINGS.get(_current_lang, _LANG_STRINGS['zh']).get(key, key)

# =============================================================================
# 配色 — V5.1: 固定亮色, 移除主题切换
# =============================================================================

COLORS = {
    # 高对比度清晰配色 — V6.0 重调
    'BG':       '#f0f0f0',   # 背景灰（稍深，和白色卡片有区分）
    'CARD':     '#ffffff',   # 白色卡片
    'ACC':      '#0078d4',   # Win11 蓝（更饱和）
    'ACC2':     '#005a9e',   # 深蓝 hover
    'TXT':      '#1a1a1a',   # 主文字（纯黑灰）
    'SUB':      '#444444',   # 次要文字（加深，确保可读）
    'SEL_BG':   '#dce8f5',   # 选中背景（淡蓝，与白色卡片有区分且不突兀）
    'SEL_FG':   '#1a1a1a',   # 选中文字
    'CUR_BG':   '#cce0f5',   # 当前设备背景（饱和度更高的蓝，一眼能看出）
    'CUR_FG':   '#0055a5',   # 当前设备文字（深蓝）
    'REC_BG':   '#fff3cd',   # 录制背景
    'REC_FG':   '#856404',   # 录制前景
    'ENTRY_BG': '#ffffff',   # 输入框背景
    'DIVIDER':  '#cccccc',   # 分割线（加深）
    'TROUGH':   '#bbbbbb',   # 滑动条轨道（明显可见）
    'HDR_FG':   '#0078d4',   # 头部前景
    'HDR_SAVED':'#0a7020',   # 已保存（Win11 绿）
}

def t(key):
    """获取颜色值。"""
    return COLORS.get(key, '#ffffff')

# =============================================================================
# 日志
# =============================================================================

logger = logging.getLogger(APP_NAME)

def setup_logging():
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(str(LOG_FILE), encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%H:%M:%S'))
    logger.addHandler(fh)
    if sys.stderr and sys.stderr.isatty():
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(logging.INFO)
        sh.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
        logger.addHandler(sh)

# =============================================================================
# 配置管理器 — 内存缓存 + 线程安全
# =============================================================================

class ConfigManager:
    """线程安全的配置管理器。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._data = dict(DEFAULT_CFG)
        self.load()

    def load(self):
        with self._lock:
            try:
                with open(CFG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for k, v in data.items():
                    self._data[k] = v
                self._migrate()
                logger.info("配置已加载")
            except FileNotFoundError:
                logger.info("配置文件不存在, 使用默认值")
            except Exception as e:
                logger.error(f"配置加载失败: {e}")

    def _migrate(self):
        """清理旧版配置键, 补充新键。"""
        changed = False
        for old_key in ('cycle_devices', 'favorite_devices', 'rules', 'automations', 'theme'):
            if old_key in self._data:
                self._data.pop(old_key, None)
                changed = True
        if 'preset_slots' in self._data and 'device_preset_slots' not in self._data:
            old_slots = self._data.pop('preset_slots')
            self._data['device_preset_slots'] = {}
            # 把所有已有设备的预设都设成旧值（兼容旧行为）
            device_volumes = self._data.get('device_volumes', {})
            for did in device_volumes:
                self._data['device_preset_slots'][did] = list(old_slots)
            if not device_volumes:
                self._data['device_preset_slots'] = {}  # 无历史设备, 空 dict
            else:
                changed = True
            logger.info(f"配置迁移: preset_slots → device_preset_slots ({len(self._data['device_preset_slots'])} 设备)")
        elif 'preset_slots' in self._data:
            # 两键并存 → 保留新键, 删旧键
            self._data.pop('preset_slots', None)
            changed = True
        for k, v in DEFAULT_CFG.items():
            if k not in self._data:
                self._data[k] = v
                changed = True
        if changed:
            logger.info("配置已清理迁移到 V5.25+ 格式")
            self._save_unlocked()

    def save(self):
        with self._lock:
            self._save_unlocked()

    def _save_unlocked(self):
        try:
            with open(CFG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            logger.info("配置已保存")
        except Exception as e:
            logger.error(f"配置保存失败: {e}")

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._data[key] = value

    def update(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                self._data[k] = v
        self.save()

    def get_all(self):
        with self._lock:
            return dict(self._data)

    def set_all(self, data):
        """V5.19: 批量替换整个配置字典。"""
        with self._lock:
            self._data = dict(data)
        self.save()

# =============================================================================
# 音频控制器 — 线程安全 COM 操作
# =============================================================================

ole32   = ctypes.windll.ole32
user32  = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32  = ctypes.windll.shell32

class _GUID(ctypes.Structure):
    _fields_ = [('D1', wintypes.DWORD), ('D2', wintypes.WORD),
                ('D3', wintypes.WORD), ('D4', ctypes.c_byte * 8)]

def _make_guid(s):
    g = _GUID()
    ole32.CLSIDFromString(s, ctypes.byref(g))
    return g

class AudioController:
    """线程安全的音频设备控制器。"""

    _lock = threading.Lock()
    _tls  = threading.local()

    CLSID_PolicyConfig = _make_guid('{870af99c-171d-4f9e-af0d-e63df40c2bc9}')
    IID_IPolicyConfig  = _make_guid('{f8679f50-850a-41cf-9c72-430f290290c8}')

    @classmethod
    def _ensure_com(cls):
        if getattr(cls._tls, 'com_init', False):
            return
        import comtypes
        comtypes.CoInitialize()
        cls._tls.com_init = True
        logger.debug(f"COM 已初始化 (thread={threading.get_ident()})")

    @classmethod
    def _get_policy(cls):
        if hasattr(cls._tls, 'set_fn'):
            return cls._tls.policy_h, cls._tls.set_fn

        cls._ensure_com()
        p = wintypes.LPVOID()
        hr = ole32.CoCreateInstance(
            ctypes.byref(cls.CLSID_PolicyConfig), None, 23,
            ctypes.byref(cls.IID_IPolicyConfig), ctypes.byref(p))
        if hr < 0 or not p.value:
            logger.error(f"CoCreateInstance 失败 hr=0x{hr & 0xFFFFFFFF:08X}")
            return None, None

        ptr_size = ctypes.sizeof(wintypes.LPVOID)
        vp = ctypes.cast(p.value, ctypes.POINTER(wintypes.LPVOID)).contents.value
        addr = vp + 13 * ptr_size
        fptr = ctypes.cast(addr, ctypes.POINTER(wintypes.LPVOID)).contents.value
        set_fn = ctypes.WINFUNCTYPE(
            ctypes.c_long, wintypes.LPVOID,
            ctypes.c_wchar_p, ctypes.c_int)(fptr)

        cls._tls.policy_h = p.value
        cls._tls.set_fn = set_fn
        return p.value, set_fn

    @classmethod
    def get_devices(cls):
        cls._ensure_com()
        with cls._lock:
            try:
                from pycaw.pycaw import AudioUtilities, AudioDeviceState
                result = []
                for d in AudioUtilities.GetAllDevices():
                    if '{0.0.0.' in d.id and d.state != AudioDeviceState.NotPresent:
                        result.append({
                            'id': d.id,
                            'name': str(d.FriendlyName),
                            'is_active': d.state == AudioDeviceState.Active,
                        })
                return result
            except Exception as e:
                logger.error(f"get_devices 失败: {e}")
                return []

    @classmethod
    def get_default_id(cls):
        cls._ensure_com()
        with cls._lock:
            try:
                from pycaw.pycaw import AudioUtilities
                eid = AudioUtilities.GetDeviceEnumerator()
                return eid.GetDefaultAudioEndpoint(0, 0).GetId()
            except Exception as e:
                logger.error(f"get_default_id 失败: {e}")
                return None

    @classmethod
    def switch_to(cls, device_id):
        """切换默认音频设备。

         去掉 0.8s 阻塞 sleep，改为 150ms 短暂等待 + 异步验证。
        验证失败不阻断用户操作（蓝牙设备等异步场景），仅记录日志。
        """
        with cls._lock:
            policy_h, set_fn = cls._get_policy()
            if not set_fn:
                return False
            try:
                for role in range(3):
                    hr = set_fn(policy_h, ctypes.c_wchar_p(device_id), role)
                    if hr < 0:
                        logger.error(f"SetDefault hr=0x{hr & 0xFFFFFFFF:08X} dev={device_id[:30]}")
                        return False
            except Exception as e:
                logger.error(f"switch_to 异常: {e}")
                return False
        # 短暂等待 Windows 音频策略生效（从 0.8s 降至 0.15s）
        time.sleep(0.15)
        # 快速验证：失败仅记录日志，不返回 False（避免误判导致用户体验差）
        try:
            actual = cls.get_default_id()
            if actual != device_id:
                logger.warning(f'switch_to 验证未通过（可能异步延迟）: 期望={device_id[:30]} 实际={actual[:30] if actual else None}')
                # 不再返回 False，让 UI 正常显示"已切换"
        except Exception:
            pass
        return True


    @classmethod
    def get_device_type_tag(cls, device_name, device_id=''):
        """根据设备名返回类型小标签：蓝牙 / 耳机 / 音箱 / 扬声器 / ''"""
        name = device_name.lower()
        # 蓝牙设备：名称含 bluetooth / 蓝牙 / BT / wireless
        if any(k in name for k in ['bluetooth', '蓝牙', 'bt ', 'bt-', 'wireless', 'ble']):
            return '蓝牙'
        # 耳机 / 耳麦
        if any(k in name for k in ['headphone', '耳机', '耳麦', 'headset', 'earphone', 'earbud', 'airpod', 'airpod']):
            return '耳机'
        # 音箱 / 扬声器
        if any(k in name for k in ['speaker', '音箱', '扬声器', 'soundbar', 'bar ', '音响']):
            return '音箱'
        # 从 device_id 判断（含 BTH 或 BTHENUM 是蓝牙）
        if 'bth' in device_id.lower() or 'bluetooth' in device_id.lower():
            return '蓝牙'
        return ''

    @classmethod
    def is_device_ready(cls, device_id):
        """检测设备是否就绪（Active 状态）。蓝牙未连接时返回 False。"""
        cls._ensure_com()
        with cls._lock:
            try:
                from pycaw.pycaw import AudioUtilities, AudioDeviceState
                for d in AudioUtilities.GetAllDevices():
                    if d.id == device_id:
                        return d.state == AudioDeviceState.Active
                return False  # 设备不存在
            except Exception as e:
                logger.error(f'is_device_ready 异常: {e}')
                return True  # 异常时保守返回 True，不阻止切换

    @classmethod
    def open_bluetooth_settings(cls):
        """打开 Windows 蓝牙设置页面。"""
        try:
            import subprocess
            subprocess.Popen('ms-settings:bluetooth', shell=True)
            return True
        except Exception as e:
            logger.error(f'打开蓝牙设置失败: {e}')
            return False

    @classmethod
    def get_device_name_map(cls):
        return {d['id']: d['name'] for d in cls.get_devices()}

    @classmethod
    def get_all_device_ids(cls):
        return [d['id'] for d in cls.get_devices()]

    @classmethod
    def get_volume(cls, device_id):
        cls._ensure_com()
        with cls._lock:
            try:
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                enumerator = AudioUtilities.GetDeviceEnumerator()
                device = enumerator.GetDevice(device_id)
                interface = device.Activate(
                    IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                vol = cast(interface, POINTER(IAudioEndpointVolume))
                return vol.GetMasterVolumeLevelScalar()
            except Exception as e:
                logger.error(f"get_volume 失败: {e}")
                return None

    @classmethod
    def set_volume(cls, device_id, level):
        cls._ensure_com()
        with cls._lock:
            try:
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                enumerator = AudioUtilities.GetDeviceEnumerator()
                device = enumerator.GetDevice(device_id)
                interface = device.Activate(
                    IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                vol = cast(interface, POINTER(IAudioEndpointVolume))
                vol.SetMasterVolumeLevelScalar(float(level), None)
                return True
            except Exception as e:
                logger.error(f"set_volume 失败: {e}")
                return False

    @classmethod
    def toggle_mute(cls, device_id):
        """切换指定设备的静音状态。"""
        cls._ensure_com()
        with cls._lock:
            try:
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                enumerator = AudioUtilities.GetDeviceEnumerator()
                device = enumerator.GetDevice(device_id)
                interface = device.Activate(
                    IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                vol = cast(interface, POINTER(IAudioEndpointVolume))
                current = vol.GetMute()  # 返回 0 或 1
                vol.SetMute(not current, None)  # pycaw 接受布尔值
                return True
            except Exception as e:
                logger.error(f"toggle_mute 失败: {e}")
                return False

    @classmethod
    def get_mute(cls, device_id):
        """获取指定设备的静音状态。"""
        cls._ensure_com()
        with cls._lock:
            try:
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                enumerator = AudioUtilities.GetDeviceEnumerator()
                device = enumerator.GetDevice(device_id)
                interface = device.Activate(
                    IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                vol = cast(interface, POINTER(IAudioEndpointVolume))
                return vol.GetMute() == 1
            except Exception as e:
                logger.error(f"get_mute 失败: {e}")
                return False

# =============================================================================
# 通知 / 开机自启 / 测试音
# =============================================================================
# 全局 Toast 通知 — V5.21: 用 GUI 内置 Toast 替代 plyer 系统通知
# =============================================================================

# 全局引用，Application.run() 中赋值
_gui_instance = None

def set_gui_ref(gui):
    """设置 GUI 实例引用，供全局 notify 使用。"""
    global _gui_instance
    _gui_instance = gui

def _get_toast_type(title):
    """根据通知标题推断 toast 类型。"""
    t = title.lower()
    if '失败' in t or 'fail' in t or 'error' in t:
        return 'error'
    if '成功' in t or '切换' in t or 'switch' in t:
        return 'success'
    if '警告' in t or 'warn' in t or '未就绪' in t:
        return 'warning'
    return 'info'

def notify(title, msg):
    """V5.21: 优先用 GUI 内置 Toast，回退到 plyer 系统通知。"""
    global _gui_instance
    # 优先走内置 toast（GUI 已创建时）
    if _gui_instance and hasattr(_gui_instance, 'root') and _gui_instance.root.winfo_exists():
        try:
            toast_type = _get_toast_type(title)
            _gui_instance.root.after(0, lambda m=msg, tt=toast_type: _gui_instance._show_toast(m, tt))
            return
        except Exception:
            pass
    # 回退到 plyer
    try:
        from plyer import notification
        notification.notify(title=title, message=msg, app_name=APP_NAME,
                            timeout=3, toast=True)
    except Exception as e:
        logger.debug(f"通知失败: {e}")

def set_auto_start(enable):
    """V5.0: 修复打包后开机自启路径。"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_WRITE)
        if enable:
            if _is_frozen():
                cmd = f'"{sys.executable}"'
            else:
                cmd = f'"{sys.executable}" "{os.path.abspath(__file__)}"'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        logger.info(f"开机自启 {'已启用' if enable else '已禁用'}")
    except Exception as e:
        logger.error(f"设置开机自启失败: {e}")

def play_test_sound():
    """V5.1: 播放更长的系统测试音效, 跨 Win10/Win11 兼容。"""
    def _play():
        try:
            import winsound
            media_dir = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Media')

            priority_sounds = [
                'Alarm01.wav', 'Alarm02.wav', 'Alarm03.wav', 'Alarm04.wav',
                'Alarm05.wav', 'Alarm06.wav', 'Alarm07.wav', 'Alarm08.wav',
                'Alarm09.wav', 'Alarm10.wav',
                'tada.wav', 'chimes.wav', 'chord.wav',
                'Windows Notify System Generic.wav',
                'Windows Notify Calendar.wav',
                'Windows Logon Sound.wav',
                'Windows Exclamation.wav',
                'Windows Critical Stop.wav',
            ]

            for sound_name in priority_sounds:
                sound_path = os.path.join(media_dir, sound_name)
                if os.path.exists(sound_path) and os.path.getsize(sound_path) > 20000:
                    winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    logger.debug(f"播放测试音效: {sound_name}")
                    return

            # 回退1: 扫描 Media 目录及其子目录, 找最长的 wav 文件
            best_file = None
            best_size = 0
            for root_dir, dirs, files in os.walk(media_dir):
                for f in files:
                    if f.lower().endswith('.wav'):
                        full = os.path.join(root_dir, f)
                        try:
                            sz = os.path.getsize(full)
                            if sz > best_size and sz > 50000:
                                best_size = sz
                                best_file = full
                        except OSError:
                            pass
            if best_file:
                winsound.PlaySound(best_file, winsound.SND_FILENAME | winsound.SND_ASYNC)
                logger.debug(f"播放回退音效: {best_file}")
                return

            # 回退2: 系统通知别名
            winsound.PlaySound('SystemNotification', winsound.SND_ALIAS | winsound.SND_ASYNC)
            return
        except Exception:
            pass
        try:
            import winsound
            winsound.MessageBeep(0x40)
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()

# =============================================================================
# 热键解析与 VK 映射表
# =============================================================================

MOD_ALT      = 0x0001
MOD_CONTROL  = 0x0002
MOD_SHIFT    = 0x0004
MOD_WIN      = 0x0008
MOD_NOREPEAT = 0x4000

VK_MAP = {
    'F1':0x70,'F2':0x71,'F3':0x72,'F4':0x73,'F5':0x74,'F6':0x75,
    'F7':0x76,'F8':0x77,'F9':0x78,'F10':0x79,'F11':0x7A,'F12':0x7B,
    '1':0x31,'2':0x32,'3':0x33,'4':0x34,'5':0x35,'6':0x36,'7':0x37,'8':0x38,'9':0x39,'0':0x30,
    'A':0x41,'B':0x42,'C':0x43,'D':0x44,'E':0x45,'F':0x46,'G':0x47,'H':0x48,'I':0x49,
    'J':0x4A,'K':0x4B,'L':0x4C,'M':0x4D,'N':0x4E,'O':0x4F,'P':0x50,'Q':0x51,'R':0x52,
    'S':0x53,'T':0x54,'U':0x55,'V':0x56,'W':0x57,'X':0x58,'Y':0x59,'Z':0x5A,
    'SPACE':0x20,'TAB':0x09,'ESC':0x1B,
    'LEFT':0x25,'UP':0x26,'RIGHT':0x27,'DOWN':0x28,
    'INSERT':0x2D,'DELETE':0x2E,'HOME':0x24,'END':0x23,'PAGEUP':0x21,'PAGEDOWN':0x22,
    'PRTSC':0x2C,'SCROLLLOCK':0x91,'PAUSE':0x13,
    'NUM0':0x60,'NUM1':0x61,'NUM2':0x62,'NUM3':0x63,'NUM4':0x64,
    'NUM5':0x65,'NUM6':0x66,'NUM7':0x67,'NUM8':0x68,'NUM9':0x69,
    'NUMMULT':0x6A,'NUMADD':0x6B,'NUMSUB':0x6D,'NUMDOT':0x6E,'NUMDIV':0x6F,
    'MEDIANEXT':0xB0,'MEDIAPREV':0xB1,'MEDIASTOP':0xB2,'MEDIAPLAY':0xB3,
    'VOLUP':0xAF,'VOLDOWN':0xAE,'VOLMUTE':0xAD,
}

MOD_VK = {
    'Ctrl':  0x11,
    'Alt':   0x12,
    'Shift': 0x10,
}
MOD_ORDER = ['Ctrl', 'Alt', 'Shift', 'Win']
MOD_NAME_TO_FLAG = {
    'Ctrl': MOD_CONTROL, 'Alt': MOD_ALT,
    'Shift': MOD_SHIFT, 'Win': MOD_WIN,
}

def parse_hotkey(hotkey_str):
    if not hotkey_str or not hotkey_str.strip():
        return None
    parts = [p.strip() for p in hotkey_str.split('+')]
    mod, vk = 0, None
    for p in parts:
        up = p.upper()
        if up in ('CTRL', 'CONTROL'):
            mod |= MOD_CONTROL
        elif up == 'ALT':
            mod |= MOD_ALT
        elif up == 'SHIFT':
            mod |= MOD_SHIFT
        elif up in ('WIN', 'WINDOWS', 'SUPER'):
            mod |= MOD_WIN
        elif up in VK_MAP:
            vk = VK_MAP[up]
        else:
            return None
    if vk is None:
        return None
    return (mod | MOD_NOREPEAT, vk)

# =============================================================================
# 热键录入控件 — GetAsyncKeyState 轮询
# =============================================================================

class HotkeyRecorder:
    """专业热键录入控件, 使用 GetAsyncKeyState 轮询捕获按键。"""

    def __init__(self, parent, initial_value='', on_change=None, root=None, width=18):
        import tkinter as tk
        self._tk = tk
        self._raw = initial_value
        self.on_change = on_change
        self._recording = False
        self._poll_id = None
        self._prev_regular = set()
        self._root = root or parent.winfo_toplevel()

        self.var = tk.StringVar(value=self._fmt(initial_value))

        self._width = width if width else 18
        self.entry = tk.Entry(parent, textvariable=self.var, width=self._width,
                              font=('Consolas', 10), justify='center',
                              readonlybackground=t('ENTRY_BG'), state='readonly',
                              cursor='hand2', relief='solid', bd=1)

        self.entry.bind('<Button-1>', self._on_click)
        self.entry.bind('<FocusIn>', self._on_click)
        self.entry.bind('<FocusOut>', self._on_focus_out)
        self.entry.bind('<Enter>', lambda e: self._style('hover'))
        self.entry.bind('<Leave>', lambda e: self._style('normal') if not self._recording else None)
        self._style('normal')

    @staticmethod
    def _fmt(val):
        return val if val else i18n('click_to_set')

    def _style(self, state):
        if self._recording:
            self.entry.config(bg=t('REC_BG'), fg=t('REC_FG'), readonlybackground=t('REC_BG'))
        elif state == 'hover':
            self.entry.config(bg=t('SEL_BG'), fg=t('TXT'), readonlybackground=t('SEL_BG'))
        else:
            self.entry.config(bg=t('ENTRY_BG'), fg=t('TXT'), readonlybackground=t('ENTRY_BG'))

    def _on_click(self, event=None):
        if self._recording:
            return 'break'
        self._start_recording()
        return 'break'

    def _on_focus_out(self, event=None):
        if self._recording:
            self._cancel()

    def _start_recording(self):
        self._recording = True
        self._prev_regular = set()
        self.var.set(i18n('recording_hint'))
        self._style('recording')
        self.entry.focus_set()
        self._poll()

    def _poll(self):
        if not self._recording:
            return

        mods_held = set()
        for mod_name, vk in MOD_VK.items():
            if user32.GetAsyncKeyState(vk) & 0x8000:
                mods_held.add(mod_name)
        if (user32.GetAsyncKeyState(0x5B) & 0x8000) or (user32.GetAsyncKeyState(0x5C) & 0x8000):
            mods_held.add('Win')

        current_regular = set()
        for key_name, vk in VK_MAP.items():
            if key_name == 'ESC':
                continue
            if user32.GetAsyncKeyState(vk) & 0x8000:
                current_regular.add(key_name)

        if mods_held:
            mod_str = '+'.join(m for m in MOD_ORDER if m in mods_held)
            self.var.set(f'{mod_str} + ?')
        else:
            self.var.set(i18n('recording_hint'))

        if user32.GetAsyncKeyState(0x1B) & 0x8000:
            self._cancel()
            return

        new_regular = current_regular - self._prev_regular

        if new_regular and mods_held:
            key = sorted(new_regular)[0]
            mod_list = [m for m in MOD_ORDER if m in mods_held]
            hk = '+'.join(mod_list + [key])
            self._accept(hk)
            return

        if new_regular and not mods_held:
            self.var.set(i18n('need_modifier'))
            self._root.after(1200, self._cancel_if_recording)

        self._prev_regular = current_regular
        self._poll_id = self._root.after(20, self._poll)

    def _cancel_if_recording(self):
        if self._recording:
            self._cancel()

    def _accept(self, hotkey_str):
        self._recording = False
        self._raw = hotkey_str
        self.var.set(hotkey_str)
        self._style('normal')
        if self.on_change:
            self.on_change(hotkey_str)

    def _cancel(self):
        self._recording = False
        if self._poll_id:
            self._root.after_cancel(self._poll_id)
            self._poll_id = None
        self.var.set(self._fmt(self._raw))
        self._style('normal')

    def get_value(self):
        return self._raw

    def set_value(self, val):
        self._raw = val
        self.var.set(self._fmt(val))
        self._recording = False
        self._style('normal')

    def clear(self):
        self._raw = ''
        self.var.set(i18n('click_to_set'))
        self._recording = False
        self._style('normal')
        if self.on_change:
            self.on_change('')

    def pack(self, **kw):  self.entry.pack(**kw)
    def grid(self, **kw):  self.entry.grid(**kw)

# =============================================================================
# 托盘图标管理器
# =============================================================================

WM_TRAYICON      = 0x0400 + 1
WM_HOTKEY_MSG    = 0x0312
WM_APP_REGISTER = 0x8001  # 请求托盘线程重新注册热键
WM_DESTROY       = 0x0002
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP     = 0x0205

NIM_ADD    = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON   = 0x00000002
NIF_TIP    = 0x00000004

MF_STRING    = 0x00000000
MF_SEPARATOR = 0x00000800
MF_POPUP     = 0x00000010
MF_GRAYED    = 0x00000002
TPM_LEFTALIGN  = 0x0000
TPM_RETURNCMD  = 0x0100

LR_LOADFROMFILE = 0x0010

user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  ctypes.c_longlong, ctypes.c_longlong]
user32.DefWindowProcW.restype  = ctypes.c_longlong

class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD), ('hWnd', wintypes.HWND),
        ('uID', wintypes.UINT), ('uFlags', wintypes.UINT),
        ('uCallbackMessage', wintypes.UINT), ('hIcon', wintypes.HICON),
        ('szTip', ctypes.c_wchar * 128), ('dwState', wintypes.DWORD),
        ('dwStateMask', wintypes.DWORD), ('szInfo', ctypes.c_wchar * 256),
        ('uVersion', wintypes.UINT), ('szInfoTitle', ctypes.c_wchar * 64),
        ('dwInfoFlags', wintypes.DWORD),
    ]

class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.UINT), ('style', wintypes.UINT),
        ('lpfnWndProc', ctypes.c_void_p), ('cbClsExtra', wintypes.INT),
        ('cbWndExtra', wintypes.INT), ('hInstance', wintypes.HINSTANCE),
        ('hIcon', wintypes.HICON), ('hCursor', wintypes.HANDLE),
        ('hbrBackground', wintypes.HANDLE), ('lpszMenuName', wintypes.LPCWSTR),
        ('lpszClassName', wintypes.LPCWSTR), ('hIconSm', wintypes.HICON),
    ]

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                              ctypes.c_longlong, ctypes.c_longlong)

class TrayManager:
    """系统托盘图标管理。"""

    def __init__(self, app):
        self.app = app
        self.hwnd = None
        self.hicon = None
        self._wndproc_ref = None
        self._hotkey_ids = {}
        self._next_hk_id = 1
        self._menu_cbs = {}
        self._menu_next_id = 1000
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name='Tray')
        self._thread.start()

    def stop(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_DESTROY, 0, 0)

    def _run(self):
        AudioController._ensure_com()
        try:
            self._create_window()
            self._load_icon()
            self._add_tray_icon()
            self._register_all_hotkeys()
            logger.info(f"托盘窗口已创建 hwnd={self.hwnd}")
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            logger.info("托盘消息循环结束")
        except Exception as e:
            logger.error(f"托盘启动失败: {e}", exc_info=True)
        finally:
            self._remove_tray_icon()

    def _create_window(self):
        self._wndproc_ref = WNDPROC(self._wnd_proc)
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = ctypes.cast(self._wndproc_ref, ctypes.c_void_p)
        wc.hInstance = hinst
        wc.lpszClassName = 'XiaoZuanFengAudioTrayWnd_v5'
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            err = kernel32.GetLastError()
            logger.warning(f"RegisterClass 失败 (可能已注册): {err}")
        # WS_POPUP = 0x80000000 — 隐藏但有效的窗口，RegisterHotKey 需要有效 hwnd
        self.hwnd = user32.CreateWindowExW(
            0, wc.lpszClassName, 'XiaoZuanFengAudioTray', 0x80000000,
            0, 0, 0, 0, 0, 0, hinst, 0)
        if not self.hwnd:
            err = kernel32.GetLastError()
            logger.error(f"CreateWindowExW 失败: err={err}")

    def _load_icon(self):
        ico = _icon_path()
        if ico.exists():
            h = user32.LoadImageW(0, str(ico), 1, 0, 0, LR_LOADFROMFILE)
            if h:
                self.hicon = h
                logger.info(f"图标已从文件加载: {ico}")
                return
            logger.warning(f"LoadImage 失败, 使用系统图标")
        self.hicon = user32.LoadIconW(0, 32512)

    def _add_tray_icon(self):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self.hicon
        nid.szTip = f'{APP_NAME}  {APP_VER}'
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    def _remove_tray_icon(self):
        if not self.hwnd:
            return
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam == WM_LBUTTONDBLCLK:
                self.app.show_gui()
            elif lparam == WM_RBUTTONUP:
                self._show_menu(hwnd)
            return 0
        elif msg == WM_HOTKEY_MSG:
            hid = wparam & 0xFFFF
            cb = self._hotkey_ids.get(hid)
            if cb:
                try:
                    cb()
                except Exception as e:
                    logger.error(f"热键回调异常: {e}")
            return 0
        elif msg == WM_APP_REGISTER:
            self._register_all_hotkeys()
            return 0
        elif msg == WM_DESTROY:
            self._remove_tray_icon()
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _get_display_name(self, device_id, dev_map):
        """V5.0: 获取设备显示名 — 优先使用别名。"""
        aliases = self.app.config.get('device_aliases', {})
        if device_id in aliases and aliases[device_id]:
            return aliases[device_id]
        return dev_map.get(device_id, device_id)

    def _show_menu(self, hwnd):
        """构建右键菜单 — V5.0: 显示别名。"""
        self._menu_cbs = {}
        self._menu_next_id = 1000
        hMenu = user32.CreatePopupMenu()
        cur = AudioController.get_default_id()
        dev_map = AudioController.get_device_name_map()
        all_devices = AudioController.get_devices()

        if all_devices:
            hSub = user32.CreatePopupMenu()
            for d in all_devices:
                display_name = self._get_display_name(d['id'], dev_map)
                short = display_name[:24] + '...' if len(display_name) > 26 else display_name
                prefix = '* ' if d['id'] == cur else '    '
                did = d['id']
                self._add_menu_item(hSub, prefix + short,
                                    lambda did=did: self._do_switch(did, dev_map))
            user32.AppendMenuW(hMenu, MF_POPUP, hSub, i18n('switch_device'))
        else:
            self._add_menu_item(hMenu, i18n('no_device_switch'), None, enabled=False)

        self._add_menu_item(hMenu, i18n('test_sound'), play_test_sound)

        cycle_hk = self.app.config.get('hotkey_cycle', '')
        if cycle_hk:
            self._add_menu_item(hMenu, f'{i18n("cycle_switch")} [{cycle_hk}]',
                                lambda: self._do_cycle_all(dev_map))

        user32.AppendMenuW(hMenu, MF_SEPARATOR, 0, None)
        self._add_menu_item(hMenu, i18n('show_main'), self.app.show_gui)
        user32.AppendMenuW(hMenu, MF_SEPARATOR, 0, None)
        self._add_menu_item(hMenu, i18n('about'),
                            lambda: self.app.gui.root.after(0, self.app.gui._show_about))
        self._add_menu_item(hMenu, i18n('donate'),
                            lambda: webbrowser.open(AFDIAN_URL))
        user32.AppendMenuW(hMenu, MF_SEPARATOR, 0, None)
        self._add_menu_item(hMenu, i18n('exit'), self.app.quit)

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(hwnd)
        cmd = user32.TrackPopupMenu(hMenu, TPM_LEFTALIGN | TPM_RETURNCMD,
                                     pt.x, pt.y, 0, hwnd, None)
        if cmd > 0 and cmd in self._menu_cbs:
            try:
                self._menu_cbs[cmd]()
            except Exception as e:
                logger.error(f"菜单回调异常: {e}")
        user32.DestroyMenu(hMenu)

    def _add_menu_item(self, hMenu, text, callback, enabled=True):
        mid = self._menu_next_id
        self._menu_next_id += 1
        if callback:
            self._menu_cbs[mid] = callback
        flags = MF_STRING if enabled else (MF_STRING | MF_GRAYED)
        user32.AppendMenuW(hMenu, flags, mid, text)
        return mid

    def _do_switch(self, device_id, dev_map):
        threading.Thread(target=self._switch_thread, args=(device_id, dev_map), daemon=True).start()

    def _switch_thread(self, device_id, dev_map):
        name = self._get_display_name(device_id, dev_map)
        # 切换前检测设备是否就绪（蓝牙未连接时给出提示）
        if not AudioController.is_device_ready(device_id):
            notify(i18n('device_not_ready'), name)
            # 仍然尝试切换，但给更明确的失败提示
        ok = AudioController.switch_to(device_id)
        if ok:
            self._apply_saved_volume(device_id)
            winsound.MessageBeep(0x40)
            notify(i18n('switched_to'), f'{i18n("current_device")}: {name}')
        else:
            notify(i18n('switch_verify_failed'), name)
        # 切换后刷新 UI；强制高亮刚切换到的设备，绕过 get_default_id() 延迟
        gui = self.app.gui
        if gui and hasattr(gui, 'root'):
            gui.root.after(0, lambda did=device_id, ok=ok: gui._refresh_devices(force_cur=did if ok else None))

    def _apply_saved_volume(self, device_id):
        try:
            vols = self.app.config.get('device_volumes', {})
            if device_id in vols:
                AudioController.set_volume(device_id, vols[device_id])
        except Exception as e:
            logger.debug(f"恢复音量失败: {e}")

    def _do_cycle_all(self, dev_map):
        all_ids = AudioController.get_all_device_ids()
        if not all_ids:
            return
        threading.Thread(target=self._cycle_thread, args=(all_ids, dev_map), daemon=True).start()

    def _cycle_thread(self, cycle_devs, dev_map):
        cur = AudioController.get_default_id()
        idx = -1
        for i, did in enumerate(cycle_devs):
            if did == cur:
                idx = i
                break
        target = cycle_devs[(idx + 1) % len(cycle_devs)]
        # 检测目标设备是否就绪
        if not AudioController.is_device_ready(target):
            notify(i18n('device_not_ready'), self._get_display_name(target, dev_map))
        ok = AudioController.switch_to(target)
        if ok:
            self._apply_saved_volume(target)
            winsound.MessageBeep(0x40)
            notify(i18n('cycle_switched'), f'{i18n("current_device")}: {self._get_display_name(target, dev_map)}')
        # 切换后刷新 UI
        gui = self.app.gui
        if gui and hasattr(gui, 'root'):
            gui.root.after(0, lambda did=target, ok=ok: gui._refresh_devices(force_cur=did if ok else None))

    def _register_all_hotkeys(self):
        self._unregister_all()
        # 诊断：检查 hwnd 是否有效
        if not self.hwnd:
            logger.error("注册热键: hwnd 无效，热键将无法工作！请重启程序。")
            return  # 不继续注册，因为一定会失败
        logger.info(f"注册热键: hwnd={self.hwnd}, thread={threading.get_ident()}")
        cfg = self.app.config.get_all()
        conflicts = []

        for dev_id, hk_str in cfg.get('hotkeys', {}).items():
            if not hk_str:
                continue
            parsed = parse_hotkey(hk_str)
            if not parsed:
                logger.warning(f"无效热键: {hk_str}")
                continue
            mod, vk = parsed
            hid = self._next_hk_id
            self._next_hk_id += 1
            if user32.RegisterHotKey(self.hwnd, hid, mod, vk):
                did = dev_id
                self._hotkey_ids[hid] = lambda d=dev_id: self._hotkey_switch(d)
                logger.info(f"热键已注册: {hk_str}")
            else:
                err = kernel32.GetLastError()
                logger.warning(f"热键注册失败: hk={hk_str}, err={err}, hwnd={self.hwnd}")
                conflicts.append(hk_str)

        cycle_hk = cfg.get('hotkey_cycle', '')
        if cycle_hk:
            parsed = parse_hotkey(cycle_hk)
            if parsed:
                mod, vk = parsed
                hid = self._next_hk_id
                self._next_hk_id += 1
                if user32.RegisterHotKey(self.hwnd, hid, mod, vk):
                    self._hotkey_ids[hid] = lambda: self._hotkey_cycle_all()
                    logger.info(f"循环热键已注册: {cycle_hk}")
                else:
                    err = kernel32.GetLastError()
                    logger.warning(f"循环热键注册失败: hk={cycle_hk}, err={err}")
                    conflicts.append(cycle_hk)

        # 静音切换热键
        mute_hk = cfg.get('hotkey_mute', '')
        if mute_hk:
            parsed = parse_hotkey(mute_hk)
            if parsed:
                mod, vk = parsed
                hid = self._next_hk_id
                self._next_hk_id += 1
                if user32.RegisterHotKey(self.hwnd, hid, mod, vk):
                    self._hotkey_ids[hid] = lambda: self._hotkey_toggle_mute()
                    logger.info(f"静音热键已注册: {mute_hk}")
                else:
                    err = kernel32.GetLastError()
                    logger.warning(f"静音热键注册失败: hk={mute_hk}, err={err}")
                    conflicts.append(mute_hk)


    def _unregister_all(self):
        for hid in list(self._hotkey_ids.keys()):
            user32.UnregisterHotKey(self.hwnd, hid)
        self._hotkey_ids.clear()
        self._next_hk_id = 1

    def reregister_hotkeys(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_APP_REGISTER, 0, 0)

    def _hotkey_switch(self, device_id):
        threading.Thread(target=self._switch_thread,
                         args=(device_id, AudioController.get_device_name_map()),
                         daemon=True).start()

    def _hotkey_cycle_all(self):
        all_ids = AudioController.get_all_device_ids()
        if not all_ids:
            return
        threading.Thread(target=self._cycle_thread,
                         args=(all_ids, AudioController.get_device_name_map()),
                         daemon=True).start()

    def _hotkey_toggle_mute(self):
        """静音热键回调：切换当前设备的静音状态。"""
        cur_id = AudioController.get_default_id()
        if not cur_id:
            logger.warning("静音热键：无当前设备")
            return
        dev_map = AudioController.get_device_name_map()
        name = self._get_display_name(cur_id, dev_map)
        if AudioController.toggle_mute(cur_id):
            is_mute = AudioController.get_mute(cur_id)
            state = i18n('muted') if is_mute else i18n('unmuted')
            notify(i18n('mute_toggle'), f'{name} {state}')
        else:
            notify(i18n('switch_failed'), name)

# =============================================================================
# 设置窗口 — V5.0: 暗色主题 + 多语言 + 设备别名
# =============================================================================

class SettingsWindow:
    """主设置窗口 — V5.1: 固定配色 + 多语言 + 设备别名。"""

    def __init__(self, app):
        import tkinter as tk
        from tkinter import ttk
        self.ttk = ttk

        self.app = app
        self.tk = tk
        self.ttk = ttk
        self.cfg = app.config.get_all()
        self.dev_hotkey_entries = {}
        self.hk_name_labels = {}
        self._last_default_id = None
        self.dev_vol_scales = {}
        self.dev_vol_vars = {}
        self.dev_vol_labels = {}
        self.dev_preset_frames = {}
        self._preset_editing = False
        self._switching = False
        self._alias_editing = False

        set_language(self.cfg.get('language', 'auto'))

        self.root = tk.Tk()
        self.root.title(f"{i18n('app_title')} {APP_VER}")
        self.root.configure(bg=t('BG'))
        self.root.resizable(False, False)

        rw, rh = 580, 740
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f'{rw}x{rh}+{(sw-rw)//2}+{(sh-rh)//2}')
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after(100, lambda: self.root.attributes('-topmost', False))
        self.root.focus_force()
        self.root.protocol('WM_DELETE_WINDOW', self.minimize)

        self._build_header()
        self._build_content()
        self._build_current_device()
        self._build_device_list()
        self._build_device_buttons()
        self._build_hotkey_section()
        self._build_options()
        self._build_footer()

        self._start_device_monitor()
        # 延迟检查启动时的热键冲突提示
        self.root.after(500, self._show_pending_conflicts)

    def _show_pending_conflicts(self):
        """显示启动时遗留的热键冲突提示。"""
        if not self.app.tray:
            return
        conflicts = getattr(self.app.tray, '_pending_conflicts', None)
        if not conflicts:
            return
        msg = i18n('hotkey_conflict') + '\n' + '\n'.join(conflicts[:3])
        if len(conflicts) > 3:
            msg += f'\n... 还有 {len(conflicts) - 3} 个'
        notify(i18n('app_title'), msg)
        # 清除，避免重复提示
        self.app.tray._pending_conflicts = []

    # ── V5.24: 极简原生 Toast — 单层面板 + 左侧彩色条 ──
    def _show_toast(self, message, toast_type='info', duration=1500):
        """屏幕顶部居中弹出，淡入淡出消失。
        toast_type: info / success / error / warning
        """
        tk = self.tk
        root = self.root

        ACCENT = {
            'info':    '#569cd6',  # 蓝
            'success': '#4ec9b0',  # 青绿
            'error':   '#f44747',  # 红
            'warning': '#ce9178',  # 暖橙
        }
        BG   = '#2b2b2b'
        FG   = '#e0e0e0'
        BAR_W = 4

        toast = tk.Toplevel(root)
        toast.overrideredirect(True)
        toast.attributes('-topmost', True)

        # 单层面板
        panel = tk.Frame(toast, bg=BG)
        panel.pack()

        # 左侧彩色条
        bar = tk.Frame(panel, bg=ACCENT.get(toast_type, ACCENT['info']), width=BAR_W)
        bar.pack(side='left', fill='y')

        # 文字
        lbl = tk.Label(panel, text=message, font=('Microsoft YaHei UI', 9),
                       bg=BG, fg=FG, padx=14, pady=10)
        lbl.pack(side='left')

        # 定位 + 淡入 (纯色无需 alpha)
        toast.update_idletasks()
        tw = toast.winfo_reqwidth()
        rx = root.winfo_rootx()
        ry = root.winfo_rooty()
        rw = root.winfo_width()
        x = rx + (rw - tw) // 2
        y = ry + 56
        toast.geometry(f'+{x}+{y}')
        toast.attributes('-alpha', 0.0)
        for i in range(1, 8):
            toast.attributes('-alpha', i / 7.0)
            toast.update()
            toast.after(20)

        # 淡出
        def _fade():
            try:
                if not toast.winfo_exists():
                    return
                for i in range(6, -1, -1):
                    toast.attributes('-alpha', i / 7.0)
                    toast.update()
                    toast.after(25)
                toast.destroy()
            except Exception:
                pass

        toast.after(duration, _fade)

    def _apply_theme(self):
        """V5.1: 重建界面 (语言切换时调用)。"""
        selected = self.selected_dev[0] if hasattr(self, 'selected_dev') else None

        self.root.configure(bg=t('BG'))

        # 销毁并重建所有内容
        for widget in self.root.winfo_children():
            widget.destroy()

        self.dev_hotkey_entries = {}
        self.dev_vol_scales = {}
        self.dev_vol_vars = {}
        self.dev_vol_labels = {}

        self._build_header()
        self._build_content()
        self._build_current_device()
        self._build_device_list()
        self._build_device_buttons()
        self._build_hotkey_section()
        self._build_options()
        self._build_footer()

        self._start_device_monitor()

    # ── 头部（ 已移除，标题合并到设备列表区）──

    def _build_header(self):
        """ header 蓝条已移除，应用标题移至设备列表标题行。"""
        pass

    # ── 内容区 ──

    def _build_content(self):
        self.content = self.tk.Frame(self.root, bg=t('BG'))
        self.content.pack(fill='both', expand=True, padx=16, pady=8)

    def _build_current_device(self):
        """V5.5: 保留兼容性空壳，顶部状态栏已移除。"""
        pass
    def _build_device_list(self):
        tk, ttk = self.tk, self.ttk
        # ── 标题行（蓝色背景，左侧软件名+版本号+提示，右侧 帮助/关于）──
        title_row = tk.Frame(self.content, bg=t('ACC'))
        title_row.pack(fill='x')
        # 左侧：软件名 + 版本 + 提示文字
        left_col = tk.Frame(title_row, bg=t('ACC'))
        left_col.pack(side='left', fill='x', expand=True, padx=16, pady=(10, 8))
        tk.Label(left_col, text=f"{i18n('app_title')} {APP_VER}",
                 font=('Microsoft YaHei UI', 12, 'bold'),
                 fg='white', bg=t('ACC'), anchor='w').pack(fill='x')
        tk.Label(left_col, text=i18n('device_hint'),
                 font=('Microsoft YaHei UI', 8), fg='#cce4ff', bg=t('ACC'), anchor='w').pack(fill='x')
        # 右侧：帮助  /  关于（白色文字）
        right_col = tk.Frame(title_row, bg=t('ACC'))
        right_col.pack(side='right', padx=(4, 16), pady=14)
        btn_style = {'font': ('Microsoft YaHei UI', 9), 'bg': t('ACC'),
                     'fg': 'white', 'cursor': 'hand2'}
        h_lbl = tk.Label(right_col, text=i18n('help'), **btn_style)
        h_lbl.pack(side='left', padx=(0, 16))
        h_lbl.bind('<Button-1>', lambda e: self._show_help())
        h_lbl.bind('<Enter>', lambda e: h_lbl.config(fg='#cce0f5', underline=True))
        h_lbl.bind('<Leave>', lambda e: [h_lbl.config(fg='white'), h_lbl.config(underline=False)])
        a_lbl = tk.Label(right_col, text=i18n('about').replace('...', ''), **btn_style)
        a_lbl.pack(side='left')
        a_lbl.bind('<Button-1>', lambda e: self._show_about())
        a_lbl.bind('<Enter>', lambda e: a_lbl.config(fg='#cce0f5', underline=True))
        a_lbl.bind('<Leave>', lambda e: [a_lbl.config(fg='white'), a_lbl.config(underline=False)])

        dev_outer = tk.Frame(self.content, bg=t('CARD'), bd=1, relief='solid')
        dev_outer.pack(fill='x', pady=(0, 6))

        self.dev_canvas = tk.Canvas(dev_outer, bg=t('CARD'), highlightthickness=0)
        dev_sb = self.ttk.Scrollbar(dev_outer, orient='vertical', command=self.dev_canvas.yview)
        self.dev_scroll = tk.Frame(self.dev_canvas, bg=t('CARD'))
        self.dev_scroll.bind('<Configure>',
                              lambda e: self.dev_canvas.configure(scrollregion=self.dev_canvas.bbox('all')))
        self._dev_win = self.dev_canvas.create_window((0, 0), window=self.dev_scroll, anchor='nw')
        self.dev_canvas.configure(yscrollcommand=dev_sb.set)
        self.dev_canvas.bind('<Configure>',
                             lambda e: self.dev_canvas.itemconfig(self._dev_win, width=e.width))
        self.dev_canvas.pack(side='left', fill='both', expand=True)
        dev_sb.pack(side='right', fill='y')

        self.selected_dev = [None]
        self.dev_labels = {}
        self.dev_rows = {}
        self.dev_display_names = {}
        self._refresh_devices()

    def _build_device_buttons(self):
        tk = self.tk
        btn_row = tk.Frame(self.content, bg=t('BG'))
        btn_row.pack(fill='x', pady=(0, 8))
        tk.Button(btn_row, text=i18n('refresh'), command=self._refresh_devices,
                  font=('Microsoft YaHei UI', 9), bg='#dddddd', fg=t('TXT'),
                  relief='flat', bd=0, cursor='hand2', padx=10, pady=3).pack(side='left')
        tk.Button(btn_row, text=i18n('test_sound'), command=play_test_sound,
                  font=('Microsoft YaHei UI', 9), bg='#dddddd', fg=t('TXT'),
                  relief='flat', bd=0, cursor='hand2', padx=10, pady=3).pack(side='left', padx=(6, 0))
        tk.Button(btn_row, text=i18n('switch_to'),
                  command=self._try_switch,
                  font=('Microsoft YaHei UI', 9, 'bold'),
                  bg=t('ACC'), fg='white', relief='flat', bd=0,
                  cursor='hand2', padx=14, pady=4).pack(side='right')

    def _build_hotkey_section(self):
        """ 全局热键 — 右边框固定对齐，文字多则向左延伸."""
        tk = self.tk

        # ── Section divider ──
        tk.Frame(self.content, bg=t('DIVIDER'), height=1).pack(fill='x', pady=(4, 6))

        card = tk.Frame(self.content, bg=t('CARD'), bd=1, relief='solid')
        card.pack(fill='x', pady=(0, 6))

        # ════ 标题（在框内）════
        tk.Label(card, text=i18n('global_hotkeys'),
                 font=('Microsoft YaHei UI', 9, 'bold'),
                 fg=t('TXT'), bg=t('CARD')).pack(anchor='w', padx=10, pady=(8, 4))

        # ════ 操作热键：一行两列 ════
        action_grid = tk.Frame(card, bg=t('CARD'))
        action_grid.pack(fill='x', padx=10, pady=(0, 4))
        action_grid.columnconfigure(0, weight=1)
        action_grid.columnconfigure(1, weight=1)

        for ci, (hk_key, label_key) in enumerate([('hotkey_cycle', 'cycle_switch'),
                                                    ('hotkey_mute', 'mute_toggle')]):
            col = tk.Frame(action_grid, bg=t('CARD'))
            col.grid(row=0, column=ci, sticky='ew', padx=(0, 8) if ci == 0 else (8, 0))
            # 右侧固定：Entry + ✕ 先 pack（右侧）
            entry = HotkeyRecorder(
                col, initial_value=self.cfg.get(hk_key, ''),
                on_change=lambda v: self._on_hotkey_changed(),
                root=self.root, width=10)
            entry.pack(side='right')
            btn = tk.Button(col, text='✕', command=entry.clear,
                            font=('Segoe UI Symbol', 8),
                            bg=t('CARD'), fg='#cc3333',
                            relief='flat', cursor='hand2',
                            padx=3, pady=0)
            btn.pack(side='right', padx=(0, 2))
            # 左侧：label 填充剩余空间，右对齐
            lbl = tk.Label(col, text=i18n(label_key) + ':',
                           font=('Microsoft YaHei UI', 9),
                           fg=t('TXT'), bg=t('CARD'), anchor='e')
            lbl.pack(side='left', fill='x', expand=True)
            if hk_key == 'hotkey_cycle':
                self.cycle_hk_entry = entry
            else:
                self.mute_hk_entry = entry

        # ══════════ 分隔线 ══════════
        self.ttk.Separator(card, orient='horizontal').pack(fill='x', padx=10, pady=5)

        # ══════════ 设备热键标题 ══════════
        tk.Label(card, text=i18n('device_hotkeys'),
                 font=('Microsoft YaHei UI', 9, 'bold'),
                 fg=t('TXT'), bg=t('CARD')).pack(anchor='w', padx=10, pady=(0, 4))

        # ══════════ 设备热键：2列grid，每行右边框固定对齐 ══════════
        devices = AudioController.get_devices()
        if devices:
            dev_grid = tk.Frame(card, bg=t('CARD'))
            dev_grid.pack(fill='x', padx=10, pady=(0, 6))
            dev_grid.columnconfigure(0, weight=1)
            dev_grid.columnconfigure(1, weight=1)

            aliases = self.cfg.get('device_aliases', {})
            dev_map = AudioController.get_device_name_map()
            total = len(devices)

            for idx, d in enumerate(devices):
                did = d['id']
                row = idx // 2
                col = idx % 2

                cell = tk.Frame(dev_grid, bg=t('CARD'))

                if total % 2 == 1 and idx == total - 1:
                    cell.grid(row=row, column=0, columnspan=2, pady=2, sticky='ew')
                    wrapper = tk.Frame(cell, bg=t('CARD'))
                    wrapper.pack()
                    target = wrapper
                else:
                    padx_val = (0, 10) if col == 0 else (10, 0)
                    cell.grid(row=row, column=col, sticky='ew', padx=padx_val, pady=2)
                    target = cell

                raw_name = dev_map.get(did, d['name'])
                display = aliases.get(did, raw_name)
                short = display[:16] + '…' if len(display) > 18 else display

                # 右侧固定：Entry + ✕ 先 pack
                entry = HotkeyRecorder(
                    target,
                    initial_value=self.cfg.get('hotkeys', {}).get(did, ''),
                    on_change=lambda v, _did=did: self._on_hotkey_changed(),
                    root=self.root, width=10)
                entry.pack(side='right')
                self.dev_hotkey_entries[did] = entry
                tk.Button(target, text='✕', command=entry.clear,
                          font=('Segoe UI Symbol', 8),
                          bg=t('CARD'), fg='#cc3333',
                          relief='flat', cursor='hand2',
                          padx=3, pady=0).pack(side='right', padx=(0, 2))

                # 左侧：label 填充剩余空间，右对齐，长文字自动左延
                name_lbl = tk.Label(target, text=f'{short}:',
                                    font=('Microsoft YaHei UI', 9),
                                    fg=t('TXT'), bg=t('CARD'), anchor='e')
                name_lbl.pack(side='left', fill='x', expand=True)
                self.hk_name_labels[did] = name_lbl

    def _build_options(self):
        tk = self.tk
        tk.Frame(self.content, bg=t('DIVIDER'), height=1).pack(fill='x', pady=(0, 8))

        opt = tk.Frame(self.content, bg=t('BG'))
        opt.pack(fill='x', pady=(0, 4))
        self.auto_var = tk.BooleanVar(value=self.cfg.get('auto_start', False))
        self.notif_var = tk.BooleanVar(value=self.cfg.get('notify', True))
        tk.Checkbutton(opt, text=i18n('auto_start'), variable=self.auto_var,
                       command=self._on_option_changed,
                       font=('Microsoft YaHei UI', 9), bg=t('BG'), fg=t('TXT'),
                       activebackground=t('BG'), selectcolor=t('CARD'),
                       cursor='hand2').pack(side='left')
        tk.Checkbutton(opt, text=i18n('show_notify'), variable=self.notif_var,
                       command=self._on_option_changed,
                       font=('Microsoft YaHei UI', 9), bg=t('BG'), fg=t('TXT'),
                       activebackground=t('BG'), selectcolor=t('CARD'),
                       cursor='hand2').pack(side='left', padx=(16, 0))

        pref_row = tk.Frame(self.content, bg=t('BG'))
        pref_row.pack(fill='x', pady=(4, 8))

        tk.Label(pref_row, text=i18n('lang_label'), font=('Microsoft YaHei UI', 9),
                 fg=t('TXT'), bg=t('BG')).pack(side='left')
        self.lang_var = tk.StringVar(value=self.cfg.get('language', 'auto'))
        for val, label in [('auto', 'Auto'), ('zh', '中文'), ('en', 'English')]:
            tk.Radiobutton(pref_row, text=label, value=val,
                           variable=self.lang_var, command=self._on_lang_changed,
                           font=('Microsoft YaHei UI', 9), bg=t('BG'), fg=t('TXT'),
                           activebackground=t('BG'), selectcolor=t('CARD'),
                           cursor='hand2').pack(side='left', padx=(4, 0))

    def _build_footer(self):
        tk = self.tk

        # ──  链接栏（GitHub / 支持 / 反馈）──
        link_bar = tk.Frame(self.content, bg=t('BG'))
        link_bar.pack(fill='x', pady=(6, 2))
        link_style = {'font': ('Microsoft YaHei UI', 8), 'bg': t('BG'),
                      'fg': '#999999', 'cursor': 'hand2'}

        # GitHub
        gh_lbl = tk.Label(link_bar, text='⭐  GitHub', **link_style)
        gh_lbl.pack(side='left', padx=(0, 12))
        gh_lbl.bind('<Button-1>', lambda e: webbrowser.open(GITHUB_URL))
        gh_lbl.bind('<Enter>', lambda e: [gh_lbl.config(fg='#0067c0'), e.widget.config(font=('Microsoft YaHei UI', 8, 'underline'))])
        gh_lbl.bind('<Leave>', lambda e: [gh_lbl.config(fg='#999999'), e.widget.config(font=('Microsoft YaHei UI', 8))])

        # 分隔
        tk.Label(link_bar, text='|', font=('Microsoft YaHei UI', 8),
                 fg='#cccccc', bg=t('BG')).pack(side='left')

        # 支持（爱发电）
        dn_lbl = tk.Label(link_bar, text='❤  支持', **link_style)
        dn_lbl.pack(side='left', padx=(12, 12))
        dn_lbl.bind('<Button-1>', lambda e: webbrowser.open(AFDIAN_URL))
        dn_lbl.bind('<Enter>', lambda e: [dn_lbl.config(fg='#0067c0'), e.widget.config(font=('Microsoft YaHei UI', 8, 'underline'))])
        dn_lbl.bind('<Leave>', lambda e: [dn_lbl.config(fg='#999999'), e.widget.config(font=('Microsoft YaHei UI', 8))])

        # 分隔
        tk.Label(link_bar, text='|', font=('Microsoft YaHei UI', 8),
                 fg='#cccccc', bg=t('BG')).pack(side='left')

        # 反馈（邮箱）
        fb_lbl = tk.Label(link_bar, text='\u2709  反馈', **link_style)
        fb_lbl.pack(side='left', padx=(12, 0))
        fb_lbl.bind('<Button-1>', lambda e: self._show_feedback())
        fb_lbl.bind('<Enter>', lambda e: [fb_lbl.config(fg='#0067c0'), e.widget.config(font=('Microsoft YaHei UI', 8, 'underline'))])
        fb_lbl.bind('<Leave>', lambda e: [fb_lbl.config(fg='#999999'), e.widget.config(font=('Microsoft YaHei UI', 8))])

        # ── 最小化 / 退出按钮 ──
        footer = tk.Frame(self.content, bg=t('BG'))
        footer.pack(fill='x', pady=(8, 4))
        tk.Button(footer, text=i18n('minimize_tray'), command=self.minimize,
                  font=('Microsoft YaHei UI', 11, 'bold'),
                  bg=t('ACC'), fg='white', relief='flat', bd=0,
                  cursor='hand2', padx=28, pady=10).pack(side='left', fill='x', expand=True)
        tk.Button(footer, text=i18n('exit'), command=self.app.quit,
                  font=('Microsoft YaHei UI', 10),
                  bg=t('CARD'), fg=t('TXT'), relief='solid', bd=1,
                  cursor='hand2', padx=24, pady=10).pack(side='right', fill='x', expand=True)

    # ── V5.1: 语言切换 ──

    def _on_lang_changed(self):
        """语言切换 — 保存配置并重建界面。"""
        new_lang = self.lang_var.get()
        self.app.config.update(language=new_lang)
        self.cfg = self.app.config.get_all()
        set_language(new_lang)
        self.root.title(f"{i18n('app_title')} {APP_VER}")
        self._apply_theme()

    # ── 自动保存 + 热键冲突检测 ──

    def _on_hotkey_changed(self):
        """V5.1: 保存热键配置, 检测不同设备间的热键冲突。"""
        from tkinter import messagebox

        cycle_val = self.cycle_hk_entry.get_value()
        mute_val  = self.mute_hk_entry.get_value()
        hk_dict = {}
        # 用于检测冲突: hotkey_str -> 功能/设备显示名
        used_hotkeys = {}

        # 检查循环切换热键
        if cycle_val:
            if cycle_val in used_hotkeys:
                messagebox.showwarning(
                    i18n('app_title'),
                    f'热键冲突!\n\n'
                    f'"{cycle_val}" 已被 "{used_hotkeys[cycle_val]}" 使用\n\n'
                    f'请设置不同的热键组合'
                )
                self.cycle_hk_entry.set_value(self.cfg.get('hotkey_cycle', ''))
                return
            used_hotkeys[cycle_val] = i18n('cycle_switch')

        # 检查静音切换热键
        if mute_val:
            if mute_val in used_hotkeys:
                messagebox.showwarning(
                    i18n('app_title'),
                    f'热键冲突!\n\n'
                    f'"{mute_val}" 已被 "{used_hotkeys[mute_val]}" 使用\n\n'
                    f'请设置不同的热键组合'
                )
                self.mute_hk_entry.set_value(self.cfg.get('hotkey_mute', ''))
                return
            used_hotkeys[mute_val] = i18n('mute_toggle')

        aliases = self.cfg.get('device_aliases', {})
        dev_map = AudioController.get_device_name_map()

        for did, entry in self.dev_hotkey_entries.items():
            val = entry.get_value()
            if not val:
                continue
            display_name = aliases.get(did, dev_map.get(did, did))
            short_name = display_name if len(display_name) <= 20 else display_name[:18] + '...'

            if val in used_hotkeys:
                # 热键冲突! 弹出警告, 恢复原值
                conflict_dev = used_hotkeys[val]
                messagebox.showwarning(
                    i18n('app_title'),
                    f'热键冲突!\n\n'
                    f'"{val}" 已被 "{conflict_dev}" 使用\n\n'
                    f'请为 "{short_name}" 设置不同的热键组合'
                )
                # 恢复为之前保存的值
                old_val = self.cfg.get('hotkeys', {}).get(did, '')
                entry.set_value(old_val)
                return
            used_hotkeys[val] = short_name
            hk_dict[did] = val

        self.app.config.update(
            hotkey_cycle=cycle_val,
            hotkey_mute=mute_val,
            hotkeys=hk_dict,
        )
        if self.app.tray:
            self.app.tray.reregister_hotkeys()
        self._show_saved()

    def _on_option_changed(self):
        self.app.config.update(
            auto_start=self.auto_var.get(),
            notify=self.notif_var.get(),
        )
        set_auto_start(self.auto_var.get())
        self._show_saved()

    def _show_saved(self):
        if hasattr(self, 'save_label'):
            self.save_label.config(text=i18n('saved'))
            self.root.after(1500, lambda: self.save_label.config(text=''))

    # ── 设备状态监控 ──

    def _start_device_monitor(self):
        self._last_default_id = AudioController.get_default_id()
        self._check_device_change()

    def _check_device_change(self):
        """ 每2秒检测默认设备变化。切换中/编辑中跳过，避免 COM 冲突。"""
        try:
            # 切换中、编辑别名/预设时，全部跳过 COM 调用
            if self._switching or self._alias_editing or self._preset_editing:
                pass
            else:
                cur = AudioController.get_default_id()
                if cur != self._last_default_id:
                    logger.debug(f"设备变化检测: {self._last_default_id} -> {cur}")
                    self._last_default_id = cur
                    self._refresh_devices()
        except Exception:
            pass
        self.root.after(2000, self._check_device_change)

    # ── V5.25: per-device 预设辅助方法 ──
    def _get_device_presets(self, device_id):
        """获取某设备的预设音量列表。"""
        cfg = self.app.config.get_all()
        all_presets = cfg.get('device_preset_slots', {})
        return list(all_presets.get(device_id, [20, 50, 80]))

    def _set_device_preset(self, device_id, index, value):
        """设置某设备的某个预设值并保存。"""
        cfg = self.app.config.get_all()
        if 'device_preset_slots' not in cfg:
            cfg['device_preset_slots'] = {}
        if device_id not in cfg['device_preset_slots']:
            cfg['device_preset_slots'][device_id] = [20, 50, 80]
        cfg['device_preset_slots'][device_id][index] = value
        self.app.config.set_all(cfg)

    def _update_preset_labels(self, parent_frame=None, device_id=None):
        """V5.25: 更新预设按钮文字。device_id 可选，未提供时反查。"""
        # 反查 device_id
        if device_id is None and parent_frame is not None:
            for vid, frame in self.dev_preset_frames.items():
                if frame is parent_frame:
                    device_id = vid
                    break
        slots = self._get_device_presets(device_id) if device_id else [20, 50, 80]
        if parent_frame is not None:
            for child in parent_frame.winfo_children():
                if isinstance(child, self.tk.Button) and hasattr(child, '_preset_index'):
                    idx = child._preset_index
                    if idx < len(slots):
                        child.config(text=f'{slots[idx]}%')

    # ── 设备列表 ──

    def _get_display_name(self, device):
        """V5.0: 获取设备显示名 — 优先别名。"""
        aliases = self.cfg.get('device_aliases', {})
        dev_id = device['id']
        if dev_id in aliases and aliases[dev_id]:
            return aliases[dev_id]
        return device['name']


    # ── V5.4: 自定义预设值 ──

    def _edit_preset_slot(self, index, btn_widget=None, device_id=None):
        """V5.20: 双击预设按钮 → Toplevel 弹窗编辑。
        用 _ready 标志位解决 overrideredirect Toplevel 初始 FocusOut 问题。
        V5.20: 保存后联动滑块（传入 device_id）。
        """
        if not btn_widget:
            return
        if hasattr(btn_widget, '_editing') and btn_widget._editing:
            return
        btn_widget._editing = True
        self._preset_editing = True

        slots = self._get_device_presets(device_id)
        old_val = slots[index] if index < len(slots) else (20 * (index + 1))
        parent = btn_widget.master

        # ── 创建无边框 Toplevel 弹窗 ──
        win = self.tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.configure(bg=t('CARD'), relief='solid', bd=1)
        win.resizable(False, False)

        # 定位到预设按钮正上方
        try:
            x = btn_widget.winfo_rootx()
            y = btn_widget.winfo_rooty()
            bw = max(btn_widget.winfo_width(), 70)
            bh = btn_widget.winfo_height()
            win.geometry(f'{bw + 30}x{bh}+{x - 15}+{y}')
        except Exception:
            pass

        win.update_idletasks()

        # ── 内部控件 ──
        entry = self.tk.Entry(
            win, width=4, font=('Microsoft YaHei UI', 8),
            justify='center', relief='flat', bd=0,
            bg=t('ENTRY_BG'), fg=t('TXT')
        )
        entry.pack(side='left', fill='both', expand=True, padx=2, pady=1)
        entry.insert(0, str(old_val))
        entry.select_range(0, 'end')

        ok_btn = self.tk.Button(
            win, text='✓', font=('Microsoft YaHei UI', 8, 'bold'),
            bg=t('ACC'), fg='white',
            relief='flat', bd=0, cursor='hand2', width=2
        )
        ok_btn.pack(side='left', fill='y', padx=(0, 1), pady=1)

        # ── 状态控制 ──
        _done = [False]
        _ready = [False]

        def _finish(new_val):
            """销毁弹窗，更新 UI。"""
            if _done[0]:
                return
            _done[0] = True
            self._preset_editing = False
            try:
                win.destroy()
            except Exception:
                pass
            btn_widget.config(text=f'{new_val}%')
            btn_widget._editing = False
            self._update_preset_labels(parent, device_id=device_id)

        def _commit(event=None):
            try:
                val_str = entry.get().strip()
                try:
                    new_val = int(val_str)
                    new_val = max(0, min(100, new_val))
                except (ValueError, TypeError):
                    new_val = old_val
                self._set_device_preset(device_id, index, new_val)
                _finish(new_val)
                if device_id:
                    self._apply_preset_to_device(device_id, new_val)
            except Exception:
                # 出错也要确保 _finish 被调用，避免 _preset_editing 卡住
                _finish(old_val)

        def _cancel(event=None):
            _finish(old_val)

        # ── 绑定：回车 / ESC / ✓ 按钮 ──
        entry.bind('<Return>', _commit)
        entry.bind('<KP_Enter>', _commit)
        entry.bind('<Escape>', _cancel)
        ok_btn.config(command=_commit)

        # ── V5.18 核心：延迟启用 FocusOut 检测 ──
        # overrideredirect Toplevel 创建瞬间会触发 FocusOut，
        # 用 _ready 标志位忽略前 300ms 的事件
        def _on_focus_out(event):
            if _done[0] or not _ready[0]:
                return
            win.after_idle(_try_commit)

        def _try_commit():
            if not _done[0]:
                _commit()

        def _set_ready():
            _ready[0] = True

        win.bind('<FocusOut>', _on_focus_out)

        # ── 弹窗被 WM 关闭时的兜底 ──
        def _on_destroy(event=None):
            if not _done[0]:
                _cancel()

        win.bind('<Destroy>', _on_destroy)

        # ── 强制获取焦点 + 延迟启用 FocusOut ──
        win.focus_force()
        entry.focus_set()
        win.after(300, _set_ready)

    def _apply_preset_by_index(self, device_id, index):
        """V5.25: 单击预设按钮 → 从 per-device 配置读取预设值再应用。"""
        slots = self._get_device_presets(device_id)
        pct = slots[index] if index < len(slots) else 20
        self._apply_preset_to_device(device_id, pct)

    def _apply_preset_to_device(self, device_id, pct):
        """单击预设按钮：应用音量到设备。"""
        cfg = self.app.config.get_all()
        vols = cfg.get('device_volumes', {})
        vol_float = pct / 100.0
        AudioController.set_volume(device_id, vol_float)
        vols[device_id] = vol_float
        cfg['device_volumes'] = vols
        self.app.config.set_all(cfg)
        # 更新 UI（含滑块位置）
        if device_id in self.dev_vol_vars:
            self.dev_vol_vars[device_id].set(pct)
        if device_id in self.dev_vol_labels:
            self.dev_vol_labels[device_id].config(text=f'{pct}%')
        if device_id in self.dev_vol_scales:
            self.dev_vol_scales[device_id].set(pct)
        aliases = cfg.get('device_aliases', {})
        display_name = aliases.get(device_id, device_id)

    def _refresh_devices(self, force_cur=None):
        """V5.5: 清晰的设备列表布局 — 每设备两行(名称行 + 预设行)。"""
        if self._preset_editing or self._alias_editing:
            return
        # 清理旧组件
        for w in self.dev_scroll.winfo_children():
            w.destroy()
        self.dev_canvas.yview_moveto(0)  # 滚动回顶部
        self.dev_labels.clear()
        self.dev_rows.clear()
        self.dev_display_names.clear()
        self.dev_vol_scales.clear()
        self.dev_vol_vars.clear()
        self.dev_vol_labels.clear()
        self.dev_preset_frames.clear()
        self.selected_dev[0] = None

        self.cfg = self.app.config.get_all()
        devices = AudioController.get_devices()
        if force_cur is not None:
            cur_def = force_cur
        else:
            cur_def = AudioController.get_default_id()
        self._last_default_id = cur_def

        # 更新顶部状态栏文本（兼容性保留，即使不可见）
        if hasattr(self, 'cur_label'):
            aliases = self.cfg.get('device_aliases', {})
            raw_cur_name = next((d['name'] for d in devices if d['id'] == cur_def), '')
            cur_name = aliases.get(cur_def, raw_cur_name) if cur_def else raw_cur_name
            try:
                self.cur_label.config(text=f'  {i18n("current_device")}:  {cur_name}')
            except Exception:
                pass

        if not devices:
            self.tk.Label(self.dev_scroll, text=i18n('no_devices'),
                          font=('Microsoft YaHei UI', 10), fg=t('SUB'),
                          bg=t('CARD')).pack(pady=20)
            return

        saved_vols = self.cfg.get('device_volumes', {})

        for idx, d in enumerate(devices):
            vid = d['id']
            is_cur = (vid == cur_def)
            row_bg = t('CUR_BG') if is_cur else t('CARD')
            row_fg = t('CUR_FG') if is_cur else t('TXT')

            # ── 设备行容器（原生风格：白色卡片+细边框） ──
            row = self.tk.Frame(self.dev_scroll, bg=row_bg,
                                cursor='hand2', relief='solid', bd=1,
                                highlightthickness=0,
                                highlightbackground=t('DIVIDER'))
            row.pack(fill='x', padx=6, pady=(3, 5))
            self.dev_rows[vid] = row

            # ── 第一行：左侧色条 + 设备名/类型标签 | 右侧音量滑块+百分比 ──
            line1 = self.tk.Frame(row, bg=row_bg)
            line1.pack(fill='x', padx=8, pady=(5, 2))

            # 左侧区域：[蓝色条] 设备名 + 类型标签
            left_area = self.tk.Frame(line1, bg=row_bg)
            left_area.pack(side='left', fill='x')

            # 当前设备：蓝色竖条
            if is_cur:
                bar = self.tk.Frame(left_area, bg=t('CUR_FG'), width=4)
                bar.pack(side='left', fill='y', padx=(0, 6))

            # 设备名（可编辑）
            display_name = self._get_display_name(d)
            self.dev_display_names[vid] = display_name
            short = display_name if len(display_name) <= 40 else display_name[:38] + '…'
            short = f'{idx+1}. {short}'
            prefix = '▸ ' if is_cur else '  '

            lbl_font = ('Microsoft YaHei UI', 10, 'bold') if is_cur else ('Microsoft YaHei UI', 9)
            lbl = self.tk.Label(left_area, text=f'{prefix}{short}',
                                font=lbl_font,
                                bg=row_bg, fg=row_fg, anchor='w',
                                justify='left')
            lbl.pack(side='left', anchor='w')

            lbl.bind('<Button-1>', lambda e, v=vid: self._select_dev(v))
            lbl.bind('<Double-Button-1>', lambda e, v=vid, dn=display_name: self._double_click_switch(v, dn))
            self.dev_labels[vid] = lbl

            # ✎ 编辑图标 — 紧贴设备名右侧，极小占地（padx=2）
            # 单击/双击编辑别名，return 'break' 阻止冒泡到切换设备
            type_lbl = self.tk.Label(left_area, text='\u270e',
                                     font=('Segoe UI Symbol', 9),
                                     bg=row_bg, fg='#888888', anchor='w',
                                     padx=2, pady=0)
            type_lbl.pack(side='left', padx=(3, 0))
            type_lbl.bind('<Enter>',
                          lambda e, l=type_lbl: l.config(fg=t('ACC'), cursor='hand2'))
            type_lbl.bind('<Leave>',
                          lambda e, l=type_lbl: l.config(fg='#888888', cursor=''))
            type_lbl.bind('<Button-1>',
                          lambda e, v=vid, dd=d: self._on_alias_click(e, v, dd))
            type_lbl.bind('<Double-Button-1>',
                          lambda e, v=vid, dd=d: self._on_alias_click(e, v, dd))

            if is_cur:
                self.selected_dev[0] = vid

            # 右侧区域：音量滑块 + 百分比
            right_area = self.tk.Frame(line1, bg=row_bg)
            right_area.pack(side='right', anchor='e', pady=(8, 0))

            # 音量值
            if vid in saved_vols:
                vol_val = int(saved_vols[vid] * 100)
            elif is_cur:
                actual = AudioController.get_volume(vid)
                vol_val = int((actual or 1.0) * 100)
            else:
                vol_val = 100

            vol_var = self.tk.IntVar(value=vol_val)

            # 音量滑块 — Windows 原生细条风格（高对比度）
            scale = self.tk.Scale(right_area, from_=0, to=100,
                                  orient='horizontal',
                                  variable=vol_var, showvalue=0,
                                  width=12, sliderlength=20,
                                  length=170, resolution=1,
                                  bg=row_bg, fg='#0078d4',
                                  troughcolor=t('TROUGH'),
                                  highlightthickness=0, bd=1,
                                  takefocus=0,
                                  sliderrelief='raised',
                                  command=lambda v, did=vid: self._on_volume_change(did, v))
            scale.pack(side='left', padx=(4, 4))

            # 百分比标签
            vol_lbl = self.tk.Label(right_area, text=f' {vol_val}%',
                                    font=('Microsoft YaHei UI', 9),
                                    bg=row_bg, fg=t('SUB'),
                                    anchor='e')
            vol_lbl.pack(side='left')

            self.dev_vol_scales[vid] = scale
            self.dev_vol_vars[vid] = vol_var
            self.dev_vol_labels[vid] = vol_lbl

            scale.bind('<ButtonRelease-1>',
                       lambda e, did=vid: self._on_volume_release(did))
            # 滑块/百分比区域也支持双击切换设备（消除右侧盲区）
            scale.bind('<Double-Button-1>',
                       lambda e, v=vid, dn=display_name: self._double_click_switch(v, dn))
            vol_lbl.bind('<Double-Button-1>',
                        lambda e, v=vid, dn=display_name: self._double_click_switch(v, dn))

            # ── 第二行：预设按钮 ──
            line2 = self.tk.Frame(row, bg=row_bg)
            line2.pack(fill='x', padx=(18, 8), pady=(0, 4))
            self.dev_preset_frames[vid] = line2

            dev_slots = self._get_device_presets(vid)
            for index, pct in enumerate(dev_slots):
                btn = self.tk.Button(
                    line2, text=f'{pct}%',
                    font=('Microsoft YaHei UI', 8),
                    bg='#dde8f5', fg='#333333',
                    relief='flat', bd=0,
                    cursor='hand2', padx=10, pady=2,
                    activebackground=t('ACC'), activeforeground='white',
                    command=lambda d=vid, idx=index: self._apply_preset_by_index(d, idx)
                )
                btn._preset_index = index
                btn.pack(side='left', padx=(0, 4))
                def _on_preset_double_click(e, idx=index, b=btn, did=vid):
                    self._edit_preset_slot(idx, b, device_id=did)
                    return 'break'
                btn.bind('<Double-Button-1>', _on_preset_double_click)

            # ── 行事件绑定 ──
            # ✎ 图标单独绑了 _on_alias_click 并 return 'break'，不会冒泡到这里
            row.bind('<Button-1>', lambda e, v=vid: self._select_dev(v))
            row.bind('<Double-Button-1>', lambda e, v=vid, dn=display_name: self._double_click_switch(v, dn))
            left_area.bind('<Button-1>', lambda e, v=vid: self._select_dev(v))
            left_area.bind('<Double-Button-1>', lambda e, v=vid, dn=display_name: self._double_click_switch(v, dn))
            right_area.bind('<Button-1>', lambda e, v=vid: self._select_dev(v))
            right_area.bind('<Double-Button-1>', lambda e, v=vid, dn=display_name: self._double_click_switch(v, dn))
            # line1 本身也要绑定（覆盖 left_area 和 right_area 之间的空隙）
            line1.bind('<Button-1>', lambda e, v=vid: self._select_dev(v))
            line1.bind('<Double-Button-1>', lambda e, v=vid, dn=display_name: self._double_click_switch(v, dn))
            line2.bind('<Button-1>', lambda e, v=vid: self._select_dev(v))
            line2.bind('<Double-Button-1>', lambda e, v=vid, dn=display_name: self._double_click_switch(v, dn))
            # lbl 的单击/双击已在上方绑定
            # 右键菜单
            row.bind('<Button-3>',
                     lambda e, v=vid, dd=d: self._on_device_rightclick(e, v, dd))
            lbl.bind('<Button-3>',
                     lambda e, v=vid, dd=d: self._on_device_rightclick(e, v, dd))
            left_area.bind('<Button-3>',
                     lambda e, v=vid, dd=d: self._on_device_rightclick(e, v, dd))
            right_area.bind('<Button-3>',
                     lambda e, v=vid, dd=d: self._on_device_rightclick(e, v, dd))

    # ── V5.0: 设备别名右键菜单 ──

    def _on_device_rightclick(self, event, vid, device):
        """右键设备行 — 弹出别名设置菜单。"""
        menu = self.tk.Menu(self.root, tearoff=0,
                            bg=t('CARD'), fg=t('TXT'),
                            activebackground=t('ACC'), activeforeground='white',
                            relief='solid', bd=1)
        aliases = self.cfg.get('device_aliases', {})
        cur_alias = aliases.get(vid, '')

        if cur_alias:
            menu.add_command(label=f'{i18n("set_alias")} ({cur_alias})',
                             command=lambda: self._edit_alias(vid, device))
            menu.add_command(label=i18n('clear_alias'),
                             command=lambda: self._clear_alias(vid))
        else:
            menu.add_command(label=i18n('set_alias'),
                             command=lambda: self._edit_alias(vid, device))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_alias_click(self, event, vid, device):
        """单击/双击 ✎ 图标 → 编辑别名。return 'break' 阻止事件传播到父级双击切换。"""
        if self._alias_editing:
            return 'break'
        self._alias_editing = True
        try:
            self._edit_alias(vid, device)
        except Exception as e:
            import traceback
            err_msg = f"打开别名对话框失败:\n{e}\n\n{traceback.format_exc()}"
            logger.error(err_msg)
            try:
                from tkinter import messagebox
                messagebox.showerror('错误', err_msg, parent=self.root)
            except Exception:
                pass
            self._alias_editing = False
        return 'break'

    def _edit_alias(self, vid, device):
        """编辑设备别名 — 卡片式自定义对话框。"""
        aliases = self.cfg.get('device_aliases', {})
        current = aliases.get(vid, '')
        original = device.get('name', '')

        tk = self.tk
        dlg = tk.Toplevel(self.root)
        dlg.title(i18n('set_alias'))
        dlg.resizable(False, False)
        dlg.configure(bg=t('CARD'))
        dlg.transient(self.root)
        dlg.attributes('-topmost', True)

        # ── 主体 ──
        body = tk.Frame(dlg, bg=t('CARD'))
        body.pack(padx=16, pady=16)
        body.pack(fill='both', expand=True)

        # 原始名称卡片 — 点击填入输入框
        orig_card = tk.Frame(body, bg='#f0f0f0', cursor='hand2')
        orig_card.pack(fill='x', padx=10, pady=8)
        orig_card.pack(fill='x', pady=(0, 12))
        orig_text = f'{i18n("device_name")}:  {original}'
        orig_lbl = tk.Label(orig_card, text=orig_text,
                            font=('Microsoft YaHei UI', 10),
                            bg='#f0f0f0', fg=t('SUB'), anchor='w')
        orig_lbl.pack(fill='x')

        # 别名标签 + 当前别名提示（如有）
        if current:
            alias_hint = f'{i18n("alias_prompt")} (当前: {current})'
        else:
            alias_hint = i18n('alias_prompt')
        tk.Label(body, text=alias_hint,
                 font=('Microsoft YaHei UI', 9),
                 bg=t('CARD'), fg=t('TXT'), anchor='w').pack(fill='x', pady=(0, 4))

        entry_var = tk.StringVar(value=current)
        entry = tk.Entry(body, textvariable=entry_var, width=34,
                         font=('Microsoft YaHei UI', 11),
                         bg='white', fg=t('TXT'),
                         insertbackground=t('TXT'),
                         relief='solid', bd=1)
        entry.pack(fill='x', pady=(0, 6), ipady=4)
        entry.select_range(0, 'end')
        entry.focus_set()

        # 安全关闭：先释放 grab 再销毁，重置编辑标志（必须在按钮创建前定义，否则 NameError）
        def _on_close():
            self._alias_editing = False
            try:
                dlg.grab_release()
            except Exception:
                pass
            dlg.destroy()

        # 点击原始名称卡片 → 填入输入框
        def _fill_original(e=None):
            entry_var.set(original)
            entry.select_range(0, 'end')
            entry.focus_set()
        orig_card.bind('<Button-1>', _fill_original)
        orig_lbl.bind('<Button-1>', _fill_original)
        # hover 效果
        orig_card.bind('<Enter>', lambda e: orig_card.config(bg='#e8e8e8'))
        orig_card.bind('<Leave>', lambda e: orig_card.config(bg='#f0f0f0'))

        # 确定
        def on_ok():
            new_alias = entry_var.get().strip()
            aliases[vid] = new_alias
            self.app.config.set('device_aliases', aliases)
            self.app.config.save()
            _on_close()
            self._refresh_devices()
            self._refresh_hotkey_display_names()
            self._show_saved()

        # ── 底部按钮行 ──
        footer = tk.Frame(dlg, bg=t('CARD'))
        footer.pack(padx=16, pady=16)
        footer.pack(fill='x')

        tk.Button(footer, text=i18n('ok'), width=7,
                  font=('Microsoft YaHei UI', 10),
                  bg=t('ACC'), fg='white',
                  activebackground=t('ACC'), activeforeground='white',
                  relief='flat', padx=4, pady=4,
                  command=on_ok).pack(side='right', padx=(6, 0))

        # 取消
        tk.Button(footer, text=i18n('cancel'), width=7,
                  font=('Microsoft YaHei UI', 10),
                  bg=t('CARD'), fg=t('SUB'),
                  activebackground='#e8e8e8', activeforeground=t('TXT'),
                  relief='flat', padx=4, pady=4,
                  command=_on_close).pack(side='right')

        dlg.protocol('WM_DELETE_WINDOW', _on_close)
        dlg.bind('<Escape>', lambda e: _on_close())

        # 居中定位后再 grab_set，避免半成品对话框锁死主窗口
        dlg.update_idletasks()
        pw, ph = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
        rx = self.root.winfo_rootx()
        ry = self.root.winfo_rooty()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        x = rx + (rw - pw) // 2
        y = ry + (rh - ph) // 2
        dlg.geometry(f'+{x}+{y}')

        # 所有 widget 构建完毕后才 grab_set
        dlg.lift()
        dlg.grab_set()
        dlg.focus_force()
        dlg.after(200, lambda: dlg.attributes('-topmost', False))

    def _clear_alias(self, vid):
        """清除设备别名。"""
        aliases = self.cfg.get('device_aliases', {})
        if vid in aliases:
            del aliases[vid]
            self.app.config.set('device_aliases', aliases)
            self.app.config.save()
            self._refresh_devices()
        self._refresh_hotkey_display_names()
        self._show_saved()

    # ── 反馈信息对话框 ──

    def _show_feedback(self):
        """弹窗显示作者信息和邮箱，代替直接发邮件。"""
        tk = self.tk
        dlg = tk.Toplevel(self.root)
        dlg.title(i18n('feedback'))
        dlg.resizable(False, False)
        dlg.configure(bg='white')
        dlg.transient(self.root)
        dlg.attributes('-topmost', True)

        # 居中
        dlg.update_idletasks()
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dw, dh = 380, 260
        dlg.geometry(f'{dw}x{dh}+{(sw-dw)//2}+{(sh-dh)//2}')

        # 标题
        tk.Label(dlg, text=i18n('feedback'),
                 font=('Microsoft YaHei UI', 13, 'bold'),
                 fg=t('ACC'), bg='white').pack(pady=(22, 6))

        # 分隔线
        tk.Frame(dlg, bg='#e8e8e8', height=1).pack(fill='x', padx=40)

        # 软件名 + 版本
        tk.Label(dlg, text=f'{APP_NAME}  {APP_VER}',
                 font=('Microsoft YaHei UI', 10, 'bold'),
                 fg=t('TXT'), bg='white').pack(pady=(14, 4))

        # 作者
        author_frame = tk.Frame(dlg, bg='white')
        author_frame.pack(pady=(8, 2))
        tk.Label(author_frame, text=i18n('author_label'),
                 font=('Microsoft YaHei UI', 9), fg='#888888', bg='white').pack(side='left')
        tk.Label(author_frame, text=APP_AUTHOR,
                 font=('Microsoft YaHei UI', 9, 'bold'), fg=t('TXT'), bg='white').pack(side='left')

        # 邮箱（可点击复制或发邮件）
        email_frame = tk.Frame(dlg, bg='white')
        email_frame.pack(pady=(2, 4))
        tk.Label(email_frame, text=i18n('contact_label'),
                 font=('Microsoft YaHei UI', 9), fg='#888888', bg='white').pack(side='left')
        email_lbl = tk.Label(email_frame, text=APP_CONTACT,
                           font=('Microsoft YaHei UI', 9, 'underline'),
                           fg=t('ACC'), bg='white', cursor='hand2')
        email_lbl.pack(side='left')
        # 点击邮箱 → 复制邮箱地址到剪贴板
        def _copy_email(e=None):
            self.root.clipboard_clear()
            self.root.clipboard_append(APP_CONTACT)
            try:
                from tkinter import messagebox
                messagebox.showinfo(i18n('feedback'), i18n('email_copied'), parent=dlg)
            except Exception:
                pass
        email_lbl.bind('<Button-1>', _copy_email)
        email_lbl.bind('<Enter>', lambda e: email_lbl.config(fg='#005a9e'))
        email_lbl.bind('<Leave>', lambda e: email_lbl.config(fg=t('ACC')))

        # 提示文字
        tk.Label(dlg, text=i18n('feedback_hint'),
                 font=('Microsoft YaHei UI', 8), fg='#aaaaaa', bg='white').pack(pady=(6, 0))

        # 关闭按钮
        tk.Frame(dlg, bg='#eeeeee', height=1).pack(fill='x', pady=(12, 0))
        btn_frame = tk.Frame(dlg, bg='white')
        btn_frame.pack(padx=40, pady=(10, 14))
        btn_frame.pack(fill='x')
        tk.Button(btn_frame, text=i18n('close'), width=12,
                  font=('Microsoft YaHei UI', 9),
                  bg=t('ACC'), fg='white',
                  relief='flat', bd=0, cursor='hand2',
                  padx=14, pady=4,
                  command=lambda: [dlg.grab_release(), dlg.destroy()]).pack()

        dlg.grab_set()
        dlg.focus_force()
        dlg.bind('<Escape>', lambda e: [dlg.grab_release(), dlg.destroy()])

    # ── 关于对话框 — V6.0 ──

    def _show_about(self):
        """显示关于对话框。"""
        tk = self.tk
        dlg = tk.Toplevel(self.root)
        dlg.title(i18n('about'))
        dlg.resizable(False, False)
        dlg.configure(bg='white')
        dlg.transient(self.root)

        # 居中
        dlg.update_idletasks()
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dw, dh = 400, 420
        dlg.geometry(f'{dw}x{dh}+{(sw-dw)//2}+{(sh-dh)//2}')

        # App 名
        tk.Label(dlg, text=APP_NAME,
                 font=('Microsoft YaHei UI', 16, 'bold'),
                 fg=t('ACC'), bg='white').pack(pady=(28, 2))

        # 版本
        tk.Label(dlg, text=f'v{APP_VER}',
                 font=('Microsoft YaHei UI', 10),
                 fg='#888888', bg='white').pack()

        # 分隔线
        tk.Frame(dlg, bg='#e8e8e8', height=1).pack(fill='x', pady=(14, 0))

        # 软件简介
        tk.Label(dlg, text=i18n('app_info'),
                 font=('Microsoft YaHei UI', 9),
                 fg=t('SUB'), bg='white',
                 justify='left', wraplength=340).pack(padx=40, pady=(14, 10))

        # 作者
        tk.Label(dlg, text=i18n('author_label') + ' ' + APP_AUTHOR,
                 font=('Microsoft YaHei UI', 8),
                 fg='#888888', bg='white').pack(anchor='w', padx=40)

        # 联系方式
        email_lbl = tk.Label(dlg, text=i18n('contact_label') + ' ' + APP_CONTACT,
                             font=('Microsoft YaHei UI', 8),
                             fg=t('ACC'), bg='white', cursor='hand2')
        email_lbl.pack(anchor='w', padx=40, pady=(4, 0))
        email_lbl.bind('<Button-1>', lambda e: webbrowser.open(f'mailto:{APP_CONTACT}'))

        # 分隔线
        tk.Frame(dlg, bg='#e8e8e8', height=1).pack(fill='x', pady=(14, 0))

        # 按钮区
        btn_frame = tk.Frame(dlg, bg='white')
        btn_frame.pack(pady=(14, 10))

        def _on_close():
            try:
                dlg.grab_release()
            except Exception:
                pass
            dlg.destroy()

        gh_btn = tk.Button(btn_frame, text='★ GitHub',
                           font=('Microsoft YaHei UI', 9),
                           bg='#f5f5f5', fg=t('TXT'),
                           relief='flat', cursor='hand2',
                           command=lambda: webbrowser.open(GITHUB_URL))
        gh_btn.pack(side='left', padx=(0, 10))

        dn_btn = tk.Button(btn_frame, text='❤ ' + i18n('donate_btn'),
                           font=('Microsoft YaHei UI', 9),
                           bg='#fff0f0', fg='#c0392b',
                           relief='flat', cursor='hand2',
                           command=lambda: webbrowser.open(AFIAN_URL))
        dn_btn.pack(side='left')

        # 关闭按钮
        tk.Button(dlg, text=i18n('close'), width=14,
                  font=('Microsoft YaHei UI', 9),
                  bg=t('ACC'), fg='white',
                  relief='flat', cursor='hand2',
                  command=_on_close).pack(pady=(10, 20))

        dlg.grab_set()
        dlg.focus_force()
        dlg.bind('<Escape>', lambda e: _on_close())
    def _show_help(self):
        """显示帮助对话框。"""
        import tkinter as tk
        dlg = tk.Toplevel(self.root)
        dlg.title(i18n('help'))
        dlg.resizable(False, False)
        dlg.configure(bg='white')
        dlg.transient(self.root)

        # 居中
        dlg.update_idletasks()
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dw, dh = 460, 520
        dlg.geometry(f'{dw}x{dh}+{(sw-dw)//2}+{(sh-dh)//2}')

        # 标题
        tk.Label(dlg, text=i18n('help'),
                 font=('Microsoft YaHei UI', 14, 'bold'),
                 fg=t('ACC'), bg='white').pack(pady=(22, 4))

        # 分隔线
        tk.Frame(dlg, bg='#e8e8e8', height=1).pack(fill='x')

        # 帮助内容区
        info = tk.Frame(dlg, bg='white')
        info.pack(fill='x', padx=40, pady=(16, 8))

        help_items = [
            (i18n('help_switch'),    i18n('help_switch_desc')),
            (i18n('help_alias'),     i18n('help_alias_desc')),
            (i18n('help_volume'),     i18n('help_volume_desc')),
            (i18n('help_preset'),    i18n('help_preset_desc')),
            (i18n('help_hotkey'),    i18n('help_hotkey_desc')),
            (i18n('help_autostart'), i18n('help_autostart_desc')),
            (i18n('help_tray'),      i18n('help_tray_desc')),
        ]

        for title, desc in help_items:
            item = tk.Frame(info, bg='white')
            item.pack(anchor='w', pady=(0, 10))
            # 左侧圆点 + 标题同行
            hdr = tk.Frame(item, bg='white')
            hdr.pack(anchor='w')
            tk.Label(hdr, text='●',
                     font=('Microsoft YaHei UI', 7),
                     fg=t('ACC'), bg='white').pack(side='left')
            tk.Label(hdr, text=f' {title}',
                     font=('Microsoft YaHei UI', 9, 'bold'),
                     fg=t('TXT'), bg='white').pack(side='left')
            # 描述文字
            tk.Label(item, text=desc,
                     font=('Microsoft YaHei UI', 8),
                     fg='#777777', bg='white',
                     anchor='w', justify='left').pack(anchor='w', padx=(12, 0), pady=(2, 0))

        # 分隔线
        tk.Frame(dlg, bg='#e8e8e8', height=1).pack(fill='x', pady=(6, 0))

        # 底部关闭按钮
        def _on_close():
            try:
                dlg.grab_release()
            except Exception:
                pass
            dlg.destroy()

        tk.Button(dlg, text=i18n('close'), width=14,
                  font=('Microsoft YaHei UI', 9),
                  bg=t('ACC'), fg='white',
                  relief='flat', cursor='hand2',
                  command=_on_close).pack(pady=(14, 20))

        dlg.grab_set()
        dlg.focus_force()
        dlg.bind('<Escape>', lambda e: _on_close())

    def _open_donate(self):
        """直接打开爱发电捐赠页。"""
        webbrowser.open(AFDIAN_URL)

    # ── 音量控制 ──

    def _on_volume_change(self, device_id, value):
        vol = int(float(value))
        if device_id in self.dev_vol_labels:
            self.dev_vol_labels[device_id].config(text=f'{vol}%')
        if device_id == self._last_default_id:
            AudioController.set_volume(device_id, vol / 100.0)

    def _on_volume_release(self, device_id):
        if device_id in self.dev_vol_vars:
            vol = self.dev_vol_vars[device_id].get()
            vols = self.app.config.get('device_volumes', {})
            vols[device_id] = vol / 100.0
            self.app.config.set('device_volumes', vols)
            self.app.config.save()
            self._show_saved()

        self._refresh_hotkey_display_names()

    def _select_dev(self, vid):
        """单击选中设备 — 视觉高亮当前选中行，当前系统默认设备用另一色。"""
        self.selected_dev[0] = vid
        cur = AudioController.get_default_id()
        for dvid, row in self.dev_rows.items():
            lbl = self.dev_labels[dvid]
            is_cur = (dvid == cur)
            if dvid == vid:
                # 用户刚单击选中的设备 → 淡蓝高亮
                bg, fg = t('SEL_BG'), t('SEL_FG')
            elif is_cur:
                # 系统当前默认设备（但未选中）→ 更浅的蓝
                bg, fg = t('CUR_BG'), t('CUR_FG')
            else:
                # 其他设备 → 白色
                bg, fg = t('CARD'), t('TXT')
            lbl.config(bg=bg, fg=fg)
            row.config(bg=bg)
            if dvid in self.dev_vol_scales:
                self.dev_vol_scales[dvid].config(bg=bg, fg=fg)
                self.dev_vol_labels[dvid].config(bg=bg, fg=fg)

    def _try_switch(self):
        """ 切换设备入口 — 互斥保护，防并发 COM 踩踏。
        V5.28: 从 UI 缓存取 display_name，避免 Toast 显示设备 ID 乱码。
        """
        if self._switching:
            return
        self._switching = True
        vid = self.selected_dev[0]
        display_name = self.dev_display_names.get(vid, '')
        threading.Thread(target=self._switch_selected, args=(display_name,), daemon=True).start()

    def _double_click_switch(self, vid, display_name=''):
        """ 双击切换 + 互斥防抖 + UI 层传入名称避免 COM 重查。"""
        if self._preset_editing:
            return
        if self._switching:
            return
        self._switching = True
        self.selected_dev[0] = vid
        threading.Thread(target=self._switch_selected, args=(display_name,), daemon=True).start()

    def _switch_selected(self, display_name=''):
        """ 后台线程切换设备 — 快速响应（总耗时 ~200ms 内）。

        display_name 从 UI 层传入，避免在后台线程再次调用 COM 枚举。
        """
        try:
            vid = self.selected_dev[0]
            if not vid:
                self.root.after(0, lambda: notify(i18n('app_title'), i18n('select_first')))
                return
            if not display_name:
                aliases = self.cfg.get('device_aliases', {})
                display_name = aliases.get(vid, vid)
            # 核心 COM 操作（switch_to 内部仅 0.15s 短暂等待）
            ok = AudioController.switch_to(vid)
            if ok:
                vols = self.app.config.get('device_volumes', {})
                if vid in vols:
                    AudioController.set_volume(vid, vols[vid])
                winsound.MessageBeep(0x40)  # 切换成功提示音
                toast_msg = f'{i18n("current_device")}: {display_name}'
                self.root.after(0, lambda: notify(i18n('switched_to'), toast_msg))
            else:
                self.root.after(0, lambda: notify(i18n('switch_failed'), display_name))
            self.root.after(150, self._refresh_devices)
            self.root.after(400, self._refresh_devices)
        except Exception as e:
            logger.error(f"_switch_selected 异常: {e}", exc_info=True)
            try:
                self.root.after(0, lambda: notify(i18n('switch_failed'), str(e)))
                self.root.after(150, self._refresh_devices)
            except Exception:
                pass
        finally:
            self._switching = False

    # ── 窗口控制 ──

    def minimize(self):
        self.root.withdraw()

    def restore(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self._refresh_devices()

    def run(self):
        self.root.mainloop()

# =============================================================================
# 应用协调器
# =============================================================================

class Application:
    """协调 ConfigManager / TrayManager / SettingsWindow。"""

    def __init__(self):
        self.config = ConfigManager()
        self.tray = None
        self.gui = None

    def run(self):
        logger.info(f'{APP_NAME} {APP_VER} 启动中...')

        self.tray = TrayManager(self)
        self.tray.start()

        self.gui = SettingsWindow(self)
        set_gui_ref(self.gui)
        self.gui.run()

        self.quit()

    def show_gui(self):
        if self.gui:
            self.gui.root.after(0, self.gui.restore)

    def quit(self):
        logger.info('正在退出...')
        if self.tray:
            self.tray.stop()
        if self.gui:
            try:
                self.gui.root.quit()
            except Exception:
                pass
        time.sleep(0.5)
        sys.exit(0)

# =============================================================================
# 入口
# =============================================================================

def _check_single_instance():
    _kernel32 = ctypes.windll.kernel32
    _mutex = _kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if _kernel32.GetLastError() == 183:
        _u32 = ctypes.windll.user32
        hwnd = _u32.FindWindowW(None, APP_NAME)
        if not hwnd:
            EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            found = [0]

            @EnumProc
            def _enum(hwnd, _):
                buf = ctypes.create_unicode_buffer(256)
                _u32.GetWindowTextW(hwnd, buf, 256)
                if '小钻风' in buf.value or 'Audio' in buf.value:
                    found[0] = hwnd
                    return False
                return True
            _u32.EnumWindows(_enum, 0)
            hwnd = found[0]
        if hwnd:
            _u32.ShowWindow(hwnd, 9)
            _u32.SetForegroundWindow(hwnd)
        else:
            _u32.MessageBoxW(None, i18n('already_running'),
                APP_NAME, 0x30)
        return False
    return True

if __name__ == '__main__':
    setup_logging()

    set_language('auto')

    if not _check_single_instance():
        sys.exit(0)

    try:
        Application().run()
    except Exception as e:
        logger.error(f"致命错误: {e}", exc_info=True)
        try:
            ctypes.windll.user32.MessageBoxW(None,
                f"{i18n('fatal_error')}:\n{e}\n\n{i18n('log_file')}: {LOG_FILE}",
                APP_NAME, 0x10)
        except Exception:
            pass
        sys.exit(1)
