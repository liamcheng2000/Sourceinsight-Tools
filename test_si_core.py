"""si_core 的快速自测：构造一个仿 Xilinx 构建目录并校验输出。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from si_core import (
    SIError,
    default_si_name,
    find_build_configs,
    generate_filelist,
    list_projects,
)


class GenerateFilelistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.trunk = self.root / "trunk"
        self.project = self.trunk / "Prj_Demo"
        self.debug = self.project / "Debug"
        self.source_root = self.trunk / "CtrlSW"

        (self.source_root / "src").mkdir(parents=True)
        (self.source_root / "inc").mkdir(parents=True)
        (self.debug / "src").mkdir(parents=True)
        (self.trunk / "BSP" / "include").mkdir(parents=True)

        (self.source_root / "src" / "main.c").write_text("int main(void){return 0;}\n")
        (self.source_root / "src" / "util.c").write_text("void util(void){}\n")
        (self.source_root / "src" / "my file.c").write_text("void spaced(void){}\n")
        (self.source_root / "inc" / "app.h").write_text("#pragma once\n")
        (self.source_root / "inc" / "types.hpp").write_text("#pragma once\n")
        self.outside_header = self.trunk / "BSP" / "include" / "xil.h"
        self.outside_header.write_text("#pragma once\n")

        (self.debug / "subdir.mk").write_text(
            "C_SRCS += \\\n"
            "../../CtrlSW/src/main.c \\\n"
            "../../CtrlSW/src/my\\ file.c\n"
        )
        (self.debug / "src" / "subdir.mk").write_text(
            "C_SRCS += ../../CtrlSW/src/util.c\n"
            "CPP_SRCS += $(BSP_DIR)/not_parseable.cpp\n"
        )

        outside = self.outside_header.as_posix()
        (self.debug / "src" / "main.d").write_text(
            "src/main.o: ../../CtrlSW/src/main.c ../../CtrlSW/inc/app.h "
            f"{outside}\n"
        )
        (self.debug / "src" / "util.d").write_text(
            "src/util.o: ../../CtrlSW/src/util.c ../../CtrlSW/inc/types.hpp \\\n"
            " ../../CtrlSW/inc/app.h\n"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_generate_and_filter(self) -> None:
        logs: list[tuple[str, str]] = []
        result = generate_filelist(
            str(self.trunk),
            "Prj_Demo",
            "CtrlSW",
            "Debug",
            logger=lambda message, level: logs.append((message, level)),
        )

        self.assertEqual(result.source_count, 3)
        self.assertEqual(result.header_count, 3)
        self.assertEqual(result.listed_count, 5)
        self.assertEqual(result.outside_count, 1)
        self.assertEqual(result.si_project_name, "SI_Demo")
        self.assertTrue(os.path.isfile(result.output_file))
        self.assertTrue(os.path.isfile(result.outside_file or ""))

        content = Path(result.output_file).read_text(encoding="utf-8-sig")
        self.assertIn("src\\main.c", content)
        self.assertIn("src\\my file.c", content)
        self.assertIn("src\\util.c", content)
        self.assertIn("inc\\app.h", content)
        self.assertIn("inc\\types.hpp", content)
        self.assertNotIn("xil.h", content)
        self.assertNotIn("not_parseable.cpp", content)

        outside = Path(result.outside_file or "").read_text(encoding="utf-8-sig")
        self.assertIn("xil.h", outside)

        absolute_lines = [
            line for line in content.splitlines() if line and not line.startswith(";")
        ]
        self.assertTrue(all(not os.path.isabs(line) for line in absolute_lines))
        self.assertTrue(any("已忽略" in message for message, _ in logs))

    def test_stale_outside_file_is_removed(self) -> None:
        first = generate_filelist(
            str(self.trunk), "Prj_Demo", "CtrlSW", "Debug"
        )
        self.assertTrue(os.path.isfile(first.outside_file or ""))

        (self.debug / "src" / "main.d").write_text(
            "src/main.o: ../../CtrlSW/src/main.c ../../CtrlSW/inc/app.h\n"
        )
        second = generate_filelist(
            str(self.trunk), "Prj_Demo", "CtrlSW", "Debug"
        )

        self.assertEqual(second.outside_count, 0)
        self.assertIsNone(second.outside_file)
        self.assertFalse(os.path.exists(first.outside_file or ""))

    def test_invalid_si_name(self) -> None:
        with self.assertRaises(SIError):
            generate_filelist(
                str(self.trunk), "Prj_Demo", "CtrlSW", "Debug", "SI:Bad"
            )

    def test_helpers(self) -> None:
        self.assertEqual(default_si_name("Prj_Example"), "SI_Example")
        self.assertEqual(default_si_name("Demo"), "SI_Demo")
        self.assertEqual(list_projects(str(self.trunk))[0], "Prj_Demo")
        self.assertIn("Debug", find_build_configs(str(self.project)))

    def test_missing_build_dir_message(self) -> None:
        with self.assertRaises(SIError) as context:
            generate_filelist(str(self.trunk), "Prj_Demo", "CtrlSW", "Release")
        self.assertIn("构建目录不存在", str(context.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
