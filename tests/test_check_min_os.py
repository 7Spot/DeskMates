"""打包检查 tools/check_min_os.py（Info.plist 写的最低系统低于包里程序文件要的，老系统上点了没反应、不说原因）：
自己拼的 Mach-O 文件头（单架构、多架构、老式版本命令、别的平台），假的 .app；再拿 venv 里真要打进包的 PySide6、shiboken6、Python 对一遍
packaging/Deskmate.spec 写的数（升级依赖把要求抬高了，跑测试就知道，不用等打包）。"""
import contextlib
import importlib.util
import io
import plistlib
import re
import shutil
import struct
import sys
import sysconfig
import tempfile
import unittest
from pathlib import Path

import config

_spec = importlib.util.spec_from_file_location("check_min_os", config.ROOT / "tools" / "check_min_os.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


def packed(v):
    return (v[0] << 16) | (v[1] << 8) | (v[2] if len(v) > 2 else 0)


def thin(minos=None, *, legacy=None, platform=1, extra_build=None, bits=64, endian="<"):
    """一个单架构 Mach-O 的头和命令表：minos 走 LC_BUILD_VERSION，legacy 走 LC_VERSION_MIN_MACOSX，中间夹一条不相干的 LC_UUID。"""
    cmds, n = b"", 0
    for plat, v in ([(platform, minos)] if minos is not None else []) + ([extra_build] if extra_build else []):
        cmds += struct.pack(endian + "IIIIII", 0x32, 24, plat, packed(v), packed((26, 0)), 0)
        n += 1
    cmds += struct.pack(endian + "II", 0x1B, 24) + b"\0" * 16
    n += 1
    if legacy is not None:
        cmds += struct.pack(endian + "IIII", 0x24, 16, packed(legacy), packed((26, 0)))
        n += 1
    magic = 0xFEEDFACF if bits == 64 else 0xFEEDFACE
    head = struct.pack(endian + "IiiIIII", magic, 0x0100000C, 0, 6, n, len(cmds), 0) + (b"\0" * 4 if bits == 64 else b"")
    return head + cmds + b"\0" * 64


def fat(*slices, wide=False):
    """多架构文件：头和架构表总是大端，各架构按 4096 对齐放在后面。wide：64 位的架构表（FAT_MAGIC_64，偏移、大小是 8 字节，每项多 4 字节保留）。"""
    table, body, start = b"", b"", 4096
    for s in slices:
        if wide:
            table += struct.pack(">iiQQII", 0x0100000C, 0, start + len(body), len(s), 12, 0)
        else:
            table += struct.pack(">iiIII", 0x0100000C, 0, start + len(body), len(s), 12)
        body += s + b"\0" * (-len(s) % 4096)
    return (struct.pack(">II", 0xCAFEBABF if wide else 0xCAFEBABE, len(slices)) + table).ljust(start, b"\0") + body


class CheckMinOsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, rel, data):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def app(self, minimum="12.0"):
        """假的 .app：主程序 11.0、绑定 26.0、Python 15.0，一个指向绑定的符号链接，一个文本文件。"""
        app = self.root / "Fake.app"
        shutil.rmtree(app, ignore_errors=True)
        info = {"CFBundleName": "Fake"}
        if minimum is not None:
            info["LSMinimumSystemVersion"] = minimum
        (app / "Contents").mkdir(parents=True, exist_ok=True)
        (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info))
        self.write("Fake.app/Contents/MacOS/Fake", fat(thin((11, 0)), thin((11, 0))))
        self.write("Fake.app/Contents/Frameworks/PySide6/QtCore.abi3.so", thin((26, 0)))
        self.write("Fake.app/Contents/Frameworks/Python.framework/Versions/3.13/Python", thin((15, 0)))
        self.write("Fake.app/Contents/Resources/readme.txt", b"not a program\n")
        link = app / "Contents" / "Resources" / "QtCore.abi3.so"
        link.symlink_to(app / "Contents" / "Frameworks" / "PySide6" / "QtCore.abi3.so")
        return app

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = check.main([str(a) for a in argv])
        return code, out.getvalue(), err.getvalue()

    def test_versions_compare_as_numbers(self):
        self.assertGreater(check.parse_version("10.13"), check.parse_version("10.9"), "按数比，不按字比")
        self.assertEqual(check.parse_version("26"), check.parse_version("26.0"))
        self.assertEqual(check.format_version((14, 4, 0)), "14.4")
        self.assertEqual(check.format_version((10, 13, 4)), "10.13.4")
        with self.assertRaises(ValueError):
            check.parse_version("macOS 26")

    def test_reads_the_minimum_from_every_kind_of_header(self):
        cases = {
            "thin64": (thin((26, 0)), (True, (26, 0, 0))),
            "thin32_big_endian_old_style": (thin(legacy=(10, 13, 4), bits=32, endian=">"), (True, (10, 13, 4))),
            "fat_takes_the_highest_slice": (fat(thin((11, 0)), thin((14, 4))), (True, (14, 4, 0))),
            "fat64_takes_the_highest_slice": (fat(thin((11, 0)), thin((26, 0, 1)), wide=True), (True, (26, 0, 1))),
            "only_ios": (thin((17, 0), platform=2), (True, None)),
            "zippered_counts_macos_only": (thin((12, 0), extra_build=(6, (15, 0))), (True, (12, 0, 0))),
            "java_class_is_not_fat": (b"\xca\xfe\xba\xbe\x00\x00\x00\x34" + b"\0" * 64, (False, None)),
            "text": (b"#!/bin/sh\necho hi\n", (False, None)),
            "empty": (b"", (False, None)),
        }
        for name, (data, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(check.macho_minos(self.write(name, data)), want)

    def test_declared_too_low_lists_the_files_and_fails(self):
        code, out, err = self.run_main(self.app("12.0"))
        self.assertEqual(code, 1, "写低了：打包要停")
        self.assertIn("写的是 12.0，有 2 个程序文件要更新的系统（最高 26.0）", err, "符号链接不重复算、文本文件不算")
        self.assertLess(err.index("要 26.0"), err.index("要 15.0"), "从高到低列")
        self.assertIn("Contents/Frameworks/PySide6/QtCore.abi3.so", err)
        self.assertIn("Contents/Frameworks/Python.framework/Versions/3.13/Python", err)
        self.assertNotIn("Resources", err)
        self.assertEqual(out, "")

    def test_declared_high_enough_passes(self):
        code, out, _ = self.run_main(self.app("26.0"))
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "最低系统 26.0：包里 3 个程序文件最高要 26.0")
        code, out, _ = self.run_main(self.app("26.1"))
        self.assertEqual(code, 0, "写高了不算错")
        self.assertIn("包里最高只要 26.0", out)
        code, out, _ = self.run_main(self.app("26.0"), "--list")
        self.assertEqual([line.split()[0] for line in out.strip().splitlines()[:3]], ["26.0", "15.0", "11.0"], "--list 每个文件一行，从高到低")

    def test_what_cannot_be_checked_exits_2(self):
        self.assertEqual(self.run_main(self.root / "Nothing.app")[0], 2, "不是 .app")
        self.assertEqual(self.run_main(self.app(None))[0], 2, "没写最低系统")
        empty = self.root / "Empty.app" / "Contents"
        empty.mkdir(parents=True)
        (empty / "Info.plist").write_bytes(plistlib.dumps({"LSMinimumSystemVersion": "26.0"}))
        self.assertEqual(self.run_main(empty.parent)[0], 2, "一个程序文件都没有")


@unittest.skipUnless(sys.platform == "darwin", "只在 Mac 上有 Mach-O")
class DeclaredFloorTests(unittest.TestCase):
    def test_spec_covers_the_bindings_and_python_that_get_bundled(self):
        """venv 里要打进包的 PySide6、shiboken6、跑测试的这个 Python：要的系统都不能比 Deskmate.spec 写的新。
        包里还有 PyInstaller 顺带收进去的库（像 Homebrew 的 liblzma），那些打包时 tools/check_min_os.py 查。"""
        import PySide6
        import shiboken6
        text = (config.ROOT / "packaging" / "Deskmate.spec").read_text(encoding="utf-8")
        m = re.search(r'"LSMinimumSystemVersion":\s*"([0-9.]+)"', text)
        self.assertIsNotNone(m, "Deskmate.spec 要写 LSMinimumSystemVersion")
        declared = check.parse_version(m.group(1))
        roots = [Path(PySide6.__path__[0]), Path(shiboken6.__path__[0])]
        if sysconfig.get_config_var("DESTSHARED"):
            roots.append(Path(sysconfig.get_config_var("DESTSHARED")))      # 这个 Python 自带的扩展模块（lib-dynload）
        prefix = sysconfig.get_config_var("PYTHONFRAMEWORKPREFIX")
        if prefix:
            roots.append(Path(prefix) / "Python.framework" / "Versions" / sysconfig.get_python_version() / "Python")
        found = []
        for root in roots:
            for path, version in (check.scan(root) if root.is_dir() else [(root, check.macho_minos(root)[1])] if root.is_file() else []):
                if version is not None:
                    found.append((version, path))
        self.assertTrue(found, "找到要打进包的程序文件")
        worst, path = max(found)
        self.assertLessEqual(worst, declared, f"{path} 要 macOS {check.format_version(worst)}，Deskmate.spec 只写了 {m.group(1)}："
                             "改 LSMinimumSystemVersion（同步 packaging/安装说明.md 的要求），或者换回按老系统编的版本")


if __name__ == "__main__":
    unittest.main()
