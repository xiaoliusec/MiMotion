# -*- coding: utf8 -*-
import sqlite3
import sys
import re

DB_FILE = "zpwx.db"


def validate_code(code):
    if not code or len(code) > 16 or len(code) < 1:
        return False
    return bool(re.match(r"^[A-Za-z0-9]+$", code))


def add_code(code, is_admin=1):
    if not validate_code(code):
        print(f"错误：验证码必须是1-16位字母或数字")
        return False

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (code, is_admin) VALUES (?, ?)", (code, is_admin))
        conn.commit()
        print(f"成功添加验证码：{code}" + ("（管理员）" if is_admin else ""))
        return True
    except sqlite3.IntegrityError:
        print(f"错误：验证码 {code} 已存在")
        return False
    finally:
        conn.close()


def list_codes():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, code, is_admin FROM users ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("暂无验证码")
        return

    print("\n验证码列表：")
    print("-" * 30)
    for row in rows:
        admin_tag = "管理员" if row[2] else "普通"
        print(f"ID: {row[0]}  验证码: {row[1]}  ({admin_tag})")
    print("-" * 30)


def delete_code(code_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (code_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()

    if affected:
        print(f"已删除ID为 {code_id} 的验证码")
    else:
        print(f"未找到ID为 {code_id} 的验证码")


def main():
    if len(sys.argv) < 2:
        print("用法：")
        print("  python manage.py add <验证码>     添加验证码")
        print("  python manage.py list            列出所有验证码")
        print("  python manage.py delete <ID>     删除验证码")
        print("\n示例：")
        print("  python manage.py add admin123    添加管理员验证码 admin123")
        print("  python manage.py add user001 0  添加普通验证码 user001")
        return

    command = sys.argv[1].lower()

    if command == "add":
        if len(sys.argv) < 3:
            print("错误：请提供验证码")
            return
        code = sys.argv[2]
        is_admin = 1
        if len(sys.argv) >= 5 and sys.argv[3].lower() == "0":
            is_admin = 0
        add_code(code, is_admin)

    elif command == "list":
        list_codes()

    elif command == "delete":
        if len(sys.argv) < 3:
            print("错误：请提供验证码ID")
            return
        try:
            code_id = int(sys.argv[2])
            delete_code(code_id)
        except ValueError:
            print("错误：ID必须是数字")

    else:
        print(f"未知命令：{command}")


if __name__ == "__main__":
    main()
