"""数学对话知识提取器 - 入口

用法：
  python main.py          # 启动 GUI
  python main.py --cli    # 命令行模式
"""
import sys
import os

# 修复打包后模块导入路径
if getattr(sys, 'frozen', False):
    bundle_dir = sys._MEIPASS
    sys.path.insert(0, bundle_dir)

import argparse


def main():
    parser = argparse.ArgumentParser(description="数学对话知识提取器")
    parser.add_argument("--cli", action="store_true", help="命令行模式")
    parser.add_argument("--file", type=str, help="要导入的对话文件路径")
    parser.add_argument("--vault", type=str, help="Obsidian 仓库路径")
    parser.add_argument("--no-ai", action="store_true", help="禁用 AI 提取，仅本地模式")
    parser.add_argument("--demo", action="store_true", help="打开内置教学示例，无需 API")
    parser.add_argument('--maintain',action='store_true',help='自动整理数学笔记库（命令行）')
    parser.add_argument('--scope',choices=('math','vault'),help='整理范围')
    parser.add_argument('--preview',action='store_true',help='仅查看方案，不写入')
    parser.add_argument('--update-existing',action='store_true',help='本次导入允许补充已有笔记；不指定时独立保存')
    parser.add_argument('--undo-maintenance',action='store_true',help='撤销最近一次整理')
    parser.add_argument("--verify-bundle", type=str, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.cli:
        try:
            run_cli(args)
        except (Exception,KeyboardInterrupt) as err:
            print('处理未完成：'+str(err),file=sys.stderr)
            sys.exit(1)
    else:
        # 必须在创建 QApplication 之前设置 WebEngine 共享 OpenGL 上下文
        from PySide6.QtCore import Qt, QCoreApplication
        try:
            QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
        except Exception:
            pass
        from ui.main_window import run_app
        sys.exit(run_app(demo=args.demo, verification_output=args.verify_bundle))


def run_cli(args):
    from core.config import Config
    from core.parser import parse_file, parse_text
    from core.services import analyze_conversation,save_import,prepare_import
    from ai.client import AIClient

    config = Config.load()
    if args.vault:
        config.vault_path = args.vault
    if args.no_ai:
        config.use_ai_extraction = False

    if not config.vault_path:
        print("错误: 请指定 --vault 或在配置文件中设置 vault_path")
        sys.exit(1)
    if args.undo_maintenance:
        from core.maintenance import undo_last_maintenance
        print('已恢复。快照：'+str(undo_last_maintenance(config)))
        return
    if args.maintain:
        from core.maintenance import build_maintenance_plan,apply_maintenance_plan
        plan=build_maintenance_plan(config,AIClient(config),args.scope,print)
        if not args.preview:apply_maintenance_plan(plan,config)
        print(plan.summary())
        if args.preview:
            for path in plan.updates:print('计划修改：'+path)
        return

    if args.file:
        conv = parse_file(args.file)
    else:
        print('请输入对话内容（Windows 按 Ctrl+Z 后回车；其他系统按 Ctrl+D 结束）：')
        text = sys.stdin.read()
        conv = parse_text(text)

    print(f"消息数: {len(conv.messages)}")

    result=analyze_conversation(conv,config,print)

    if result.error:
        print(f"错误: {result.error}")
        sys.exit(1)

    print(f"is_math: {result.is_math}, score: {result.math_score:.2f}")
    print(f"提取到 {len(result.concepts)} 个知识点")

    if not result.is_math or not result.concepts:
        return

    if args.preview:
        print(prepare_import(result,config,print,update_existing=args.update_existing).diff())
        return
    counts, directory, map_title = save_import(result,config,print,update_existing=args.update_existing)
    print(f"新增 {counts['created']} / 更新 {counts['updated']} / 跳过 {counts['skipped']}")
    print(f"知识地图: {map_title}\n笔记已保存到: {directory}")


if __name__ == "__main__":
    main()
