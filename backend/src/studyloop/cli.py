"""Operator-only account commands: python -m studyloop.cli grant-admin EMAIL."""

import argparse
import sys

import psycopg

from studyloop.registration import EmailInput, connect
from studyloop.settings import Settings


def main() -> int:
    parser = argparse.ArgumentParser(description="StudyLoop 服务器账号管理")
    commands = parser.add_subparsers(dest="command", required=True)
    grant = commands.add_parser("grant-admin", help="授予已验证且启用账号管理员权限")
    grant.add_argument("email")
    args = parser.parse_args()
    try:
        email = EmailInput(email=args.email).email
        with connect(Settings.from_env()) as connection:
            user = connection.execute(
                "SELECT id FROM users WHERE email = %s AND email_verified AND enabled FOR UPDATE",
                (email,),
            ).fetchone()
            if not user:
                print("授权失败：账号必须存在、已验证邮箱且处于启用状态。", file=sys.stderr)
                return 1
            connection.execute("UPDATE users SET role = 'admin' WHERE id = %s", (user["id"],))
    except ValueError:
        print("授权失败：请检查邮箱格式与后端配置。", file=sys.stderr)
        return 1
    except psycopg.Error:
        print("授权失败：数据库暂不可用，请检查服务。", file=sys.stderr)
        return 1
    print("管理员权限已授予；重复执行保持相同结果。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
