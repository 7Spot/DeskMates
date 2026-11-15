"""打包检查：Info.plist 写的最低系统（LSMinimumSystemVersion）不能低于包里任何一个程序文件要的系统。

为什么：系统比程序文件要的老时，dyld 直接不加载它（built for macOS 26.0 which is newer than running OS），app 点了没反应、
不说原因；Info.plist 写对了，老系统在打开之前就会提示版本太低。包里 PySide6 6.12 的绑定、shiboken6 和
Homebrew 的 liblzma 却要 26.0（Homebrew 的 Python 要 15.0，Qt 本身 14.4）。
怎么查：.app 里每个普通文件（符号链接不跟，它指着的文件本身也在包里）按 Mach-O 读开，单架构、多架构（fat）都看，取 LC_BUILD_VERSION
（只认 macOS 平台）的 minos 和老式 LC_VERSION_MIN_MACOSX 的 version，一个文件取它各架构里最高的。只读文件头，不用 otool。
用法：python tools/check_min_os.py <某个.app> [--list]
  过了打一行「最低系统 X：包里 N 个程序文件最高要 Y」，退出码 0；写低了按要的系统从高到低列出文件，退出码 1；
  读不了（不是 .app、没写最低系统、一个程序文件都没有）退出码 2。--list：每个程序文件和它要的系统都列出来。
tools/build_app.sh 在卸载助手放进包以后、签名以前调它：写低了打包就停在这里（构建号退回原来的）。"""
from __future__ import annotations

import argparse
import os
import plistlib
import struct
import sys
from collections import defaultdict
from pathlib import Path
from typing import BinaryIO, Optional

Version = tuple[int, int, int]

MH_MAGIC, MH_MAGIC_64 = 0xFEEDFACE, 0xFEEDFACF     # 单架构的头：按文件自己的字节序读出来是这两个
FAT_MAGIC, FAT_MAGIC_64 = 0xCAFEBABE, 0xCAFEBABF   # 多架构的头：总是大端
MAX_FAT_ARCHS = 32                                 # Java 的 .class 也以 CAFEBABE 开头（后面是版本号，四五十）：架构数大得离谱的不当 Mach-O
LC_VERSION_MIN_MACOSX, LC_BUILD_VERSION = 0x24, 0x32
PLATFORM_MACOS = 1
SHOW_PER_VERSION = 8                               # 写低了：每个版本最多列这么多个文件，全部的用 --list 看


def parse_version(text: str) -> Version:
    """"26" / "14.4" / "10.13.4" → 三段的元组（按数比，10.13 比 10.9 新）。"""
    parts = [int(p) for p in str(text).strip().split(".")]
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"不是版本号：{text!r}")
    return tuple(parts + [0] * (3 - len(parts)))   # type: ignore[return-value]


def format_version(v: Optional[Version]) -> str:
    if v is None:
        return "?"
    return f"{v[0]}.{v[1]}" + (f".{v[2]}" if v[2] else "")


def _unpack_packed(n: int) -> Version:
    """Mach-O 里的版本号压在一个 32 位数里：xxxx.yy.zz。"""
    return (n >> 16, (n >> 8) & 0xFF, n & 0xFF)


def _thin_minos(f: BinaryIO, offset: int) -> tuple[bool, Optional[Version]]:
    """offset 处的单架构 Mach-O：(是不是 Mach-O, 要的最低 macOS；两种命令都没有就 None)。"""
    f.seek(offset)
    head = f.read(32)
    if len(head) < 28:
        return False, None
    for endian in "<>":
        magic = struct.unpack(endian + "I", head[:4])[0]
        if magic in (MH_MAGIC, MH_MAGIC_64):
            break
    else:
        return False, None
    ncmds, sizeofcmds = struct.unpack(endian + "II", head[16:24])
    f.seek(offset + (32 if magic == MH_MAGIC_64 else 28))
    cmds = f.read(sizeofcmds)
    best: Optional[Version] = None
    pos = 0
    for _ in range(ncmds):
        if pos + 8 > len(cmds):
            break
        cmd, size = struct.unpack_from(endian + "II", cmds, pos)
        found = None
        if cmd == LC_BUILD_VERSION and size >= 16 and pos + 16 <= len(cmds):        # cmd, cmdsize, platform, minos, sdk, ntools
            platform, minos = struct.unpack_from(endian + "II", cmds, pos + 8)
            found = _unpack_packed(minos) if platform == PLATFORM_MACOS else None
        elif cmd == LC_VERSION_MIN_MACOSX and size >= 12 and pos + 12 <= len(cmds):  # cmd, cmdsize, version, sdk
            found = _unpack_packed(struct.unpack_from(endian + "I", cmds, pos + 8)[0])
        if found is not None and (best is None or found > best):
            best = found
        if size < 8:                                    # 坏的命令表：别死循环
            break
        pos += size
    return True, best


def macho_minos(path: Path) -> tuple[bool, Optional[Version]]:
    """一个文件：(是不是 Mach-O, 要的最低 macOS)。多架构的取各架构里最高的；是 Mach-O 但没写版本（很老的工具链）是 (True, None)。"""
    with open(path, "rb") as f:
        head = f.read(8)
        if len(head) < 8:
            return False, None
        magic, nfat = struct.unpack(">II", head)
        if magic not in (FAT_MAGIC, FAT_MAGIC_64):
            return _thin_minos(f, 0)
        if not 0 < nfat <= MAX_FAT_ARCHS:
            return False, None
        entry, layout = (32, ">iiQQII") if magic == FAT_MAGIC_64 else (20, ">iiIII")
        table = f.read(nfat * entry)
        if len(table) < nfat * entry:
            return False, None
        offsets = [struct.unpack_from(layout, table, i * entry)[2] for i in range(nfat)]
        results = [_thin_minos(f, off) for off in offsets]
        if not any(ok for ok, _ in results):
            return False, None
        versions = [v for _, v in results if v is not None]
        return True, max(versions) if versions else None


def scan(app: Path) -> list[tuple[Path, Optional[Version]]]:
    """包里所有程序文件和它们要的系统（不跟符号链接）。"""
    out = []
    for folder, _dirs, files in os.walk(app, followlinks=False):
        for name in files:
            path = Path(folder) / name
            if path.is_symlink() or not path.is_file():
                continue
            try:
                ok, version = macho_minos(path)
            except OSError:
                continue
            if ok:
                out.append((path, version))
    return out


def declared_minimum(app: Path) -> Optional[str]:
    """Info.plist 里写的 LSMinimumSystemVersion（没写 None）；不是 .app 抛 FileNotFoundError。"""
    with open(app / "Contents" / "Info.plist", "rb") as fh:
        value = plistlib.load(fh).get("LSMinimumSystemVersion")
    return None if value in (None, "") else str(value)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Info.plist 的 LSMinimumSystemVersion 不能低于包里程序文件要的系统")
    ap.add_argument("app", type=Path, help="要查的 .app")
    ap.add_argument("--list", action="store_true", help="每个程序文件和它要的系统都列出来")
    args = ap.parse_args(argv)
    app: Path = args.app
    try:
        text = declared_minimum(app)
    except (FileNotFoundError, NotADirectoryError):
        print(f"不是 .app：找不到 {app / 'Contents' / 'Info.plist'}", file=sys.stderr)
        return 2
    if text is None:
        print("Info.plist 里没写 LSMinimumSystemVersion：老系统上点了没反应、不说原因。写在 packaging/Deskmate.spec 的 info_plist 里", file=sys.stderr)
        return 2
    declared = parse_version(text)
    files = scan(app)
    if not files:
        print(f"{app} 里一个程序文件都没有：不像打好的包", file=sys.stderr)
        return 2
    if args.list:
        for path, version in sorted(files, key=lambda pv: (pv[1] or (0, 0, 0), str(pv[0])), reverse=True):
            print(f"{format_version(version):>8}  {path.relative_to(app)}")
    known = [v for _, v in files if v is not None]
    highest = max(known) if known else None
    unknown = len(files) - len(known)
    note = f"，{unknown} 个没写" if unknown else ""
    too_new = [(p, v) for p, v in files if v is not None and v > declared]
    if not too_new:
        line = f"最低系统 {format_version(declared)}：包里 {len(files)} 个程序文件最高要 {format_version(highest)}{note}"
        if highest is not None and highest < declared:
            line += f"（写的比要的高：包里最高只要 {format_version(highest)}）"
        print(line)
        return 0
    print(f"LSMinimumSystemVersion 写的是 {format_version(declared)}，有 {len(too_new)} 个程序文件要更新的系统（最高 {format_version(highest)}）："
          f"写低了老系统上点了没反应、不说原因。改 packaging/Deskmate.spec 的 LSMinimumSystemVersion，或者换成按老系统编的依赖", file=sys.stderr)
    groups: dict[Version, list[Path]] = defaultdict(list)
    for path, version in too_new:
        groups[version].append(path)
    for version in sorted(groups, reverse=True):
        paths = sorted(str(p.relative_to(app)) for p in groups[version])
        print(f"  要 {format_version(version)}（{len(paths)} 个）：", file=sys.stderr)
        for p in paths[:SHOW_PER_VERSION]:
            print(f"    {p}", file=sys.stderr)
        if len(paths) > SHOW_PER_VERSION:
            print(f"    … 还有 {len(paths) - SHOW_PER_VERSION} 个（--list 看全部）", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
