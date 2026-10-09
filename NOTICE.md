# Notices

## epson_print_conf

PadReset is built on **epson_print_conf** by Ircama
(<https://github.com/Ircama/epson_print_conf>), Copyright (c) 2024-2025 Ircama,
licensed under the European Union Public Licence v1.2 (EUPL-1.2).

- `third_party/epson_print_conf/epson_print_conf.py` is the upstream file from
  tag v8.2.0 (commit 6873e9e2ebf73530a5a2e32f7485a0292e4d2d83), **unmodified**.
  Its licence is in `third_party/epson_print_conf/LICENSE`.
- The rest of this repository (the `padreset` package: user interface, printer
  discovery, pre-write checks, backup/verify/restore logic, packaging) was
  written for PadReset, first published 2026-10, and depends on that file.
  Together they form a derivative work distributed under EUPL-1.2.

The printer model database, EEPROM read/write keys and reset values all come
from epson_print_conf. PadReset does not add or guess any printer parameters.

## Trademarks

PadReset is an independent open-source project. It is **not affiliated with,
endorsed by, or sponsored by Seiko Epson Corporation**. "Epson" and printer
model names are trademarks of their respective owners and are used only to
describe which printers the software works with.

## No warranty

Provided "as is", without warranty of any kind (EUPL-1.2, articles 7 and 8).
Resetting the counter does not service the waste ink pad: clean or replace the
pad first, or ink may leak.

---

# 声明

- 核心功能基于 Ircama 的开源项目 epson_print_conf（EUPL-1.2）。
  `third_party/epson_print_conf/epson_print_conf.py` 为上游 v8.2.0 原文件，未作修改。
- 本仓库其余部分（界面、打印机查找、写入前核对、备份/核实/恢复、打包）为 PadReset 新写，
  与上述文件共同构成衍生作品，按 EUPL-1.2 发布。
- 型号数据、读写密钥和清零数值全部来自 epson_print_conf，本工具不添加、不猜测任何参数。
- 本工具与精工爱普生（Seiko Epson）公司无任何关联。"Epson" 及型号名称为其所有者的商标，仅用于说明适用的打印机。
- 按"现状"提供，不作任何担保。清零不等于处理废墨垫：请先清洗或更换废墨垫，否则可能漏墨。
