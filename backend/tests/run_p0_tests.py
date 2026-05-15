"""简易测试运行器 - DNA + 神经电流 + 心智架构 单元测试"""
from __future__ import annotations

import importlib
import inspect
import sys
import traceback

# P0 + P1 + P2 测试模块
TEST_MODULES = [
    # P0
    "tests.unit.services.test_dna_service",
    "tests.unit.services.test_neural_current",
    # P1
    "tests.unit.services.test_emotion_reservoir",
    "tests.unit.services.test_cooling_buffer",
    "tests.unit.services.test_emotion_state_machine",
    "tests.unit.services.test_drive_competition",
    "tests.unit.services.test_emotion_epigenetics",
    # P2
    "tests.unit.services.test_spatial_perception",
    "tests.unit.services.test_environment_behavior",
]


def discover_test_classes(module):
    """从模块中发现所有以 Test 开头的类"""
    classes = []
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if name.startswith("Test") and obj.__module__ == module.__name__:
            classes.append((name, obj))
    return sorted(classes, key=lambda x: x[0])


def discover_test_methods(cls):
    """从类中发现所有以 test_ 开头的方法"""
    methods = []
    for name, obj in inspect.getmembers(cls, predicate=inspect.isfunction):
        if name.startswith("test_"):
            methods.append(name)
    # 保持方法在源码中的定义顺序
    return methods


def run_tests():
    passed = 0
    failed = 0
    errors = 0
    failures_detail = []

    for module_name in TEST_MODULES:
        print(f"\n{'='*60}")
        print(f"Module: {module_name}")
        print(f"{'='*60}")

        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            print(f"  IMPORT ERROR: {e}")
            errors += 1
            failures_detail.append((module_name, "import", str(e), traceback.format_exc()))
            continue

        test_classes = discover_test_classes(module)
        if not test_classes:
            print("  No test classes found.")
            continue

        for cls_name, cls in test_classes:
            print(f"\n  {cls_name}:")

            try:
                instance = cls()
            except Exception as e:
                print(f"    SETUP ERROR: {e}")
                errors += 1
                failures_detail.append((cls_name, "setup", str(e), traceback.format_exc()))
                continue

            for method_name in discover_test_methods(cls):
                full_name = f"{cls_name}.{method_name}"
                try:
                    getattr(instance, method_name)()
                    print(f"    PASS {method_name}")
                    passed += 1
                except AssertionError as e:
                    print(f"    FAIL {method_name}: {e}")
                    failed += 1
                    failures_detail.append((full_name, "assertion", str(e), ""))
                except Exception as e:
                    print(f"    ERROR {method_name}: {e}")
                    errors += 1
                    failures_detail.append((full_name, "error", str(e), traceback.format_exc()))

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {errors} errors")
    print(f"{'='*60}")

    if failures_detail:
        print("\nDetails:")
        for name, kind, msg, tb in failures_detail:
            print(f"\n  [{kind}] {name}")
            print(f"    {msg.split(chr(10))[0]}")
            if tb:
                # 只显示最后5行
                lines = tb.strip().split('\n')
                for line in lines[-4:]:
                    print(f"    {line}")

    return failed == 0 and errors == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
