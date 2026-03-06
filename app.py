# -*- coding: utf8 -*-
import os
import re
import secrets
import sqlite3
import random
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler
import jwt

from zpwx import (
    login_access_token,
    grant_login_tokens,
    post_fake_brand_data,
    get_beijing_time,
)
import pytz

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

JWT_SECRET_FILE = "jwt_secret.txt"
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

if os.path.exists(JWT_SECRET_FILE):
    with open(JWT_SECRET_FILE, "r") as f:
        JWT_SECRET = f.read().strip()
else:
    JWT_SECRET = secrets.token_hex(32)
    with open(JWT_SECRET_FILE, "w") as f:
        f.write(JWT_SECRET)

DB_FILE = "zpwx.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            is_admin INTEGER DEFAULT 0,
            is_super_admin INTEGER DEFAULT 0,
            session_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user TEXT NOT NULL,
            password TEXT NOT NULL,
            app_token TEXT,
            user_id_zepp TEXT,
            device_id TEXT,
            is_phone INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS step_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            step_value TEXT NOT NULL,
            is_random INTEGER DEFAULT 0,
            is_batch INTEGER DEFAULT 0,
            result TEXT,
            error_msg TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT NOT NULL,
            detail TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            task_type TEXT NOT NULL,
            step_value TEXT NOT NULL,
            execution_time TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            last_run_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]

    if count == 0:
        cursor.execute("INSERT INTO users (code, is_admin, is_super_admin) VALUES (?, ?, ?)", ("wxyd@zeep123", 1, 1))
        logger.info("初始化默认超级管理员验证码: wxyd@zeep123")

    conn.commit()
    conn.close()


init_db()


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def get_client_ip():
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


def log_operation(user_id, username, action, detail=""):
    try:
        beijing_tz = pytz.timezone("Asia/Shanghai")
        created_at = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO operation_logs (user_id, username, action, detail, ip_address, user_agent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                user_id,
                username,
                action,
                detail,
                get_client_ip(),
                request.headers.get("User-Agent", "")[:500],
                created_at,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"日志记录失败: {e}")


def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "未认证，请先验证"}), 401

        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            request.db_user_id = payload.get("user_id")
            session_id = payload.get("session_id")

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT session_id FROM users WHERE id = ?", (request.db_user_id,)
            )
            row = cursor.fetchone()
            conn.close()

            if not row or row["session_id"] != session_id:
                return jsonify({"error": "账号已在别处登录，请刷新页面重新验证"}), 401

        except jwt.ExpiredSignatureError:
            return jsonify({"error": "认证已过期，请重新验证"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "无效的认证"}), 401

        return f(*args, **kwargs)

    return decorated


def is_admin(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row and row["is_admin"] == 1


def is_super_admin(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT is_super_admin FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row and row["is_super_admin"] == 1


def get_user_code(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT code FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row["code"] if row else None


def validate_code(code):
    if not code or len(code) > 16 or len(code) < 1:
        return False
    return True


def validate_int(value, field_name):
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ValueError(f"无效的{field_name}")


def format_user_display(user):
    if not user:
        return "未知"
    if "@" in user:
        return user[:2] + "***@" + user.split("@")[-1]
    return user[-4:].rjust(len(user), "*")


def get_beijing_now():
    beijing_tz = pytz.timezone("Asia/Shanghai")
    return datetime.now(beijing_tz)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/verify-code", methods=["POST"])
def verify_code():
    data = request.json
    code = data.get("code", "").strip()

    if not code:
        return jsonify({"error": "请输入验证码"}), 400

    if not validate_code(code):
        return jsonify({"error": "验证码格式错误"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, is_admin, is_super_admin FROM users WHERE code = ?", (code,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        log_operation(None, code, "login", "登录失败-验证码无效")
        return jsonify({"error": "验证码无效"}), 400

    user_id = row["id"]
    is_admin_user = row["is_admin"]
    is_super_admin_user = row["is_super_admin"]

    new_session_id = secrets.token_hex(16)
    cursor.execute(
        "UPDATE users SET session_id = ? WHERE id = ?", (new_session_id, user_id)
    )
    conn.commit()
    conn.close()

    payload = {
        "user_id": user_id,
        "session_id": new_session_id,
        "is_admin": is_admin_user,
        "is_super_admin": is_super_admin_user,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    log_operation(user_id, code, "login", "登录成功")

    return jsonify(
        {
            "success": True,
            "token": token,
            "isAdmin": is_admin_user == 1,
            "isSuperAdmin": is_super_admin_user == 1,
            "expiresIn": JWT_EXPIRY_HOURS * 3600,
        }
    )


@app.route("/api/admin/codes", methods=["POST"])
@jwt_required
def handle_codes():
    data = request.json
    action = data.get("action", "list")

    if not is_admin(request.db_user_id):
        return jsonify({"error": "无权限"}), 403

    conn = get_db()
    cursor = conn.cursor()

    if action == "list":
        cursor.execute(
            "SELECT id, code, is_admin, is_super_admin, created_at FROM users ORDER BY created_at DESC"
        )
        codes = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify({"codes": codes})

    elif action == "create":
        new_code = data.get("code", "").strip()
        is_admin_flag = data.get("isAdmin", 0)

        if not validate_code(new_code):
            return jsonify({"error": "验证码必须是1-16位字母或数字"}), 400

        if is_admin_flag == 1 and not is_super_admin(request.db_user_id):
            conn.close()
            return jsonify({"error": "只有超级管理员才能添加管理员验证码"}), 403

        try:
            cursor.execute("INSERT INTO users (code, is_admin) VALUES (?, ?)", (new_code, is_admin_flag))
            conn.commit()
            code_id = cursor.lastrowid
            log_operation(
                request.db_user_id,
                get_user_code(request.db_user_id),
                "create_code",
                f"创建验证码: {new_code}" + ("（管理员）" if is_admin_flag else ""),
            )
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"error": "验证码已存在"}), 400
        conn.close()
        return jsonify(
            {"success": True, "code": {"id": code_id, "code": new_code, "is_admin": is_admin_flag}}
        )

    elif action == "reset":
        target_user_id = data.get("userId")
        new_code = data.get("code", "").strip()

        if not target_user_id or not new_code:
            conn.close()
            return jsonify({"error": "参数不完整"}), 400

        if not validate_code(new_code):
            conn.close()
            return jsonify({"error": "验证码必须是1-16位字母或数字"}), 400

        cursor.execute("SELECT is_admin, is_super_admin FROM users WHERE id = ?", (target_user_id,))
        target_user = cursor.fetchone()

        if not target_user:
            conn.close()
            return jsonify({"error": "用户不存在"}), 404

        if not is_admin(request.db_user_id):
            conn.close()
            return jsonify({"error": "无权限"}), 403

        if target_user["is_super_admin"] == 1:
            conn.close()
            return jsonify({"error": "不能重置超级管理员验证码"}), 403

        if target_user["is_admin"] == 1 and not is_super_admin(request.db_user_id):
            conn.close()
            return jsonify({"error": "只有超级管理员才能重置管理员验证码"}), 403

        try:
            cursor.execute("UPDATE users SET code = ? WHERE id = ?", (new_code, target_user_id))
            conn.commit()
            log_operation(
                request.db_user_id,
                get_user_code(request.db_user_id),
                "reset_code",
                f"重置用户ID {target_user_id} 的验证码",
            )
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"error": "验证码已存在"}), 400

        conn.close()
        return jsonify({"success": True})

    return jsonify({"error": "无效操作"}), 400


@app.route("/api/admin/code/reset", methods=["POST"])
@jwt_required
def reset_code():
    data = request.json
    target_user_id = data.get("userId")
    new_code = data.get("code", "").strip()

    try:
        target_user_id = validate_int(target_user_id, "用户ID")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if not new_code:
        return jsonify({"error": "请输入新验证码"}), 400

    if not validate_code(new_code):
        return jsonify({"error": "验证码必须是1-16位字母或数字"}), 400

    if not is_admin(request.db_user_id):
        return jsonify({"error": "无权限"}), 403

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT is_admin, is_super_admin FROM users WHERE id = ?", (target_user_id,))
    target_user = cursor.fetchone()

    if not target_user:
        conn.close()
        return jsonify({"error": "用户不存在"}), 404

    if target_user["is_super_admin"] == 1:
        conn.close()
        return jsonify({"error": "不能重置超级管理员验证码"}), 403

    if target_user["is_admin"] == 1 and not is_super_admin(request.db_user_id):
        conn.close()
        return jsonify({"error": "只有超级管理员才能重置管理员验证码"}), 403

    try:
        cursor.execute("UPDATE users SET code = ? WHERE id = ?", (new_code, target_user_id))
        conn.commit()
        log_operation(
            request.db_user_id,
            get_user_code(request.db_user_id),
            "reset_code",
            f"重置用户ID {target_user_id} 的验证码",
        )
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "验证码已存在"}), 400

    conn.close()
    return jsonify({"success": True})


@app.route("/api/code/change", methods=["POST"])
@jwt_required
def change_own_code():
    data = request.json
    old_code = data.get("oldCode", "").strip()
    new_code = data.get("newCode", "").strip()

    if not old_code or not new_code:
        return jsonify({"error": "请输入旧验证码和新验证码"}), 400

    if not validate_code(new_code):
        return jsonify({"error": "验证码必须是1-16位字母或数字"}), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT code FROM users WHERE id = ?", (request.db_user_id,))
    current_code = cursor.fetchone()

    if not current_code:
        conn.close()
        return jsonify({"error": "用户不存在"}), 404

    if current_code["code"] != old_code:
        conn.close()
        return jsonify({"error": "旧验证码错误"}), 400

    try:
        cursor.execute("UPDATE users SET code = ? WHERE id = ?", (new_code, request.db_user_id))
        conn.commit()
        log_operation(
            request.db_user_id,
            old_code,
            "change_code",
            f"修改验证码: {old_code} -> {new_code}",
        )
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "验证码已存在"}), 400

    conn.close()
    return jsonify({"success": True})


@app.route("/api/admin/code/delete", methods=["POST"])
@jwt_required
def delete_code():
    if not is_admin(request.db_user_id):
        return jsonify({"error": "无权限"}), 403

    data = request.json
    code_id = data.get("id")

    try:
        code_id = validate_int(code_id, "验证码ID")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if code_id == request.db_user_id:
        return jsonify({"error": "不能删除当前使用的验证码"}), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT is_admin, is_super_admin FROM users WHERE id = ?", (code_id,))
    target_user = cursor.fetchone()

    if not target_user:
        conn.close()
        return jsonify({"error": "验证码不存在"}), 404

    if target_user["is_admin"] == 1:
        if not is_super_admin(request.db_user_id):
            conn.close()
            return jsonify({"error": "只有超级管理员才能删除其他管理员验证码"}), 403

        if target_user["is_super_admin"] == 1:
            conn.close()
            return jsonify({"error": "不能删除超级管理员验证码"}), 403

    cursor.execute("DELETE FROM users WHERE id = ?", (code_id,))
    conn.commit()
    log_operation(
        request.db_user_id,
        get_user_code(request.db_user_id),
        "delete_code",
        f"删除验证码ID: {code_id}",
    )
    conn.close()

    return jsonify({"success": True})


@app.route("/api/accounts", methods=["POST"])
@jwt_required
def handle_accounts():
    data = request.json
    action = data.get("action", "list")

    conn = get_db()
    cursor = conn.cursor()

    if action == "list":
        cursor.execute(
            "SELECT id, user, is_phone, created_at FROM accounts WHERE user_id = ? ORDER BY created_at DESC",
            (request.db_user_id,),
        )
        accounts = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify({"accounts": accounts})

    elif action == "add":
        user = data.get("user", "").strip()
        password = data.get("password", "").strip()

        if not user or not password:
            conn.close()
            return jsonify({"error": "账号和密码不能为空"}), 400

        device_id = secrets.token_hex(8)

        if not user.startswith("+86"):
            if "@" in user:
                is_phone = False
            else:
                user = "+86" + user
                is_phone = True
        else:
            is_phone = True

        access_token, msg = login_access_token(user, password)
        if access_token is None:
            conn.close()
            log_operation(
                request.db_user_id,
                get_user_code(request.db_user_id),
                "add_account",
                f"添加账号失败: {msg}",
            )
            return jsonify({"error": f"登录失败：{msg}"}), 401

        login_token, app_token, user_id_zepp, msg = grant_login_tokens(
            access_token, device_id, is_phone
        )
        if login_token is None:
            conn.close()
            log_operation(
                request.db_user_id,
                get_user_code(request.db_user_id),
                "add_account",
                f"添加账号失败: {msg}",
            )
            return jsonify({"error": f"获取token失败：{msg}"}), 401

        try:
            cursor.execute(
                """
                INSERT INTO accounts (user_id, user, password, app_token, user_id_zepp, device_id, is_phone)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    request.db_user_id,
                    user,
                    password,
                    app_token,
                    user_id_zepp,
                    device_id,
                    1 if is_phone else 0,
                ),
            )
            conn.commit()
            account_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"error": "该账号已添加"}), 400

        user_display = (
            user[-4:].rjust(len(user), "*")
            if not "@" in user
            else user[:2] + "***@" + user.split("@")[-1]
        )

        log_operation(
            request.db_user_id,
            get_user_code(request.db_user_id),
            "add_account",
            f"添加账号成功: {user_display}",
        )
        conn.close()

        return jsonify(
            {
                "success": True,
                "account": {
                    "id": account_id,
                    "user": user_display,
                    "isPhone": is_phone,
                },
            }
        )

    conn.close()
    return jsonify({"error": "无效操作"}), 400


@app.route("/api/account/delete", methods=["POST"])
@jwt_required
def delete_account():
    data = request.json
    account_id = data.get("id")

    try:
        account_id = validate_int(account_id, "账号ID")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT user FROM accounts WHERE id = ? AND user_id = ?",
        (account_id, request.db_user_id),
    )
    row = cursor.fetchone()
    if row:
        user_display = row["user"]
        if "@" in user_display:
            user_display = user_display[:2] + "***@" + user_display.split("@")[-1]
        else:
            user_display = user_display[-4:].rjust(len(user_display), "*")

    cursor.execute(
        "DELETE FROM accounts WHERE id = ? AND user_id = ?",
        (account_id, request.db_user_id),
    )
    conn.commit()

    if row:
        log_operation(
            request.db_user_id,
            get_user_code(request.db_user_id),
            "delete_account",
            f"删除账号: {user_display}",
        )

    conn.close()
    return jsonify({"success": True})


@app.route("/api/set-step", methods=["POST"])
@jwt_required
def set_step():
    data = request.json
    account_id = data.get("accountId")
    step = str(data.get("step", "")).strip()

    if not account_id:
        return jsonify({"error": "请选择账号"}), 400

    try:
        account_id = validate_int(account_id, "账号ID")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if not step.isdigit() or int(step) <= 0:
        return jsonify({"error": "步数必须大于0"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user, password, app_token, user_id_zepp, is_phone FROM accounts WHERE id = ? AND user_id = ?",
        (account_id, request.db_user_id),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "账号不存在"}), 404

    app_token = row["app_token"]
    user_id_zepp = row["user_id_zepp"]
    password = row["password"]

    if not app_token or not user_id_zepp:
        return jsonify(
            {"error": "账号未完成认证，请重新添加", "needReLogin": True}
        ), 400

    ok, msg = post_fake_brand_data(step, app_token, user_id_zepp)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user FROM accounts WHERE id = ?", (account_id,))
    account_row = cursor.fetchone()
    account_user_display = (
        format_user_display(account_row["user"]) if account_row else "未知"
    )

    if ok:
        cursor.execute(
            """
            INSERT INTO step_history (user_id, account_id, step_value, is_random, is_batch, result, error_msg)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (request.db_user_id, account_id, step, 0, 0, "success", ""),
        )
        conn.commit()
        conn.close()

        log_operation(
            request.db_user_id,
            get_user_code(request.db_user_id),
            "set_step",
            f"账号[{account_user_display}]修改步数成功: {step}",
        )
        return jsonify({"success": True, "message": f"修改步数成功！当前步数：{step}"})
    else:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user, password, is_phone FROM accounts WHERE id = ?", (account_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({"error": "账号不存在"}), 404

        user = row["user"]
        password = row["password"]
        is_phone = bool(row["is_phone"])
        account_user_display = format_user_display(user)

        device_id = secrets.token_hex(8)
        access_token, msg = login_access_token(user, password)
        if access_token is None:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO step_history (user_id, account_id, step_value, is_random, is_batch, result, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (request.db_user_id, account_id, step, 0, 0, "fail", "登录失败"),
            )
            conn.commit()
            conn.close()
            log_operation(
                request.db_user_id,
                get_user_code(request.db_user_id),
                "set_step",
                f"账号[{account_user_display}]修改步数失败: 登录失败",
            )
            return jsonify({"error": f"登录失败，请重新添加账号"}), 401

        login_token, new_app_token, new_user_id_zepp, msg = grant_login_tokens(
            access_token, device_id, is_phone
        )
        if login_token is None:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO step_history (user_id, account_id, step_value, is_random, is_batch, result, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (request.db_user_id, account_id, step, 0, 0, "fail", "获取token失败"),
            )
            conn.commit()
            conn.close()
            log_operation(
                request.db_user_id,
                get_user_code(request.db_user_id),
                "set_step",
                f"账号[{account_user_display}]修改步数失败: 获取token失败",
            )
            return jsonify({"error": f"获取token失败，请重新添加账号"}), 401

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE accounts SET app_token = ?, user_id_zepp = ?, device_id = ?, updated_at = ?
            WHERE id = ?
        """,
            (
                new_app_token,
                new_user_id_zepp,
                device_id,
                get_beijing_now().isoformat(),
                account_id,
            ),
        )
        conn.commit()
        conn.close()

        ok2, msg2 = post_fake_brand_data(step, new_app_token, new_user_id_zepp)
        if ok2:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO step_history (user_id, account_id, step_value, is_random, is_batch, result, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    request.db_user_id,
                    account_id,
                    step,
                    0,
                    0,
                    "success",
                    "重新登录后成功",
                ),
            )
            conn.commit()
            conn.close()
            log_operation(
                request.db_user_id,
                get_user_code(request.db_user_id),
                "set_step",
                f"账号[{account_user_display}]修改步数成功(重新登录): {step}",
            )
            return jsonify(
                {
                    "success": True,
                    "message": f"已为您重新登录，修改步数成功！当前步数：{step}",
                }
            )
        else:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO step_history (user_id, account_id, step_value, is_random, is_batch, result, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (request.db_user_id, account_id, step, 0, 0, "fail", msg2),
            )
            conn.commit()
            conn.close()
            log_operation(
                request.db_user_id,
                get_user_code(request.db_user_id),
                "set_step",
                f"账号[{account_user_display}]修改步数失败: {msg2}",
            )
            return jsonify({"error": f"修改步数失败：{msg2}"}), 400


@app.route("/api/batch-set-step", methods=["POST"])
@jwt_required
def batch_set_step():
    data = request.json
    account_ids = data.get("accountIds", [])
    step_value = str(data.get("stepValue", "")).strip()
    step_type = data.get("stepType", "fixed")

    if not account_ids:
        return jsonify({"error": "请选择账号"}), 400

    if not isinstance(account_ids, list):
        return jsonify({"error": "账号ID列表格式错误"}), 400

    if step_type == "fixed":
        if not step_value.isdigit() or int(step_value) <= 0:
            return jsonify({"error": "步数必须大于0"}), 400
    elif step_type == "random":
        if "-" not in step_value:
            return jsonify({"error": "随机步数请输入范围，如：10000-20000"}), 400
        try:
            parts = step_value.split("-")
            min_step = int(parts[0])
            max_step = int(parts[1])
            if min_step <= 0 or max_step <= 0 or min_step >= max_step:
                return jsonify(
                    {"error": "步数范围最小值必须大于0，且最大值要大于最小值"}
                ), 400
        except:
            return jsonify({"error": "步数范围格式错误"}), 400

    is_random = 1 if step_type == "random" else 0
    final_step = step_value
    actual_step = step_value

    conn = get_db()
    cursor = conn.cursor()

    results = []
    success_accounts = []
    for account_id in account_ids:
        try:
            account_id = validate_int(account_id, "账号ID")
        except ValueError:
            results.append(
                {"accountId": account_id, "result": "fail", "error": "无效的账号ID"}
            )
            continue

        cursor.execute(
            "SELECT user, password, app_token, user_id_zepp, is_phone FROM accounts WHERE id = ? AND user_id = ?",
            (account_id, request.db_user_id),
        )
        row = cursor.fetchone()

        if not row:
            results.append(
                {"accountId": account_id, "result": "fail", "error": "账号不存在"}
            )
            continue

        account_user = row["user"]
        account_user_display = format_user_display(account_user)

        if step_type == "random" and "-" in step_value:
            try:
                parts = step_value.split("-")
                min_step = int(parts[0])
                max_step = int(parts[1])
                actual_step = str(random.randint(min_step, max_step))
            except:
                results.append(
                    {
                        "accountId": account_id,
                        "result": "fail",
                        "error": "步数范围格式错误",
                    }
                )
                continue

        app_token = row["app_token"]
        user_id_zepp = row["user_id_zepp"]
        password = row["password"]

        if not app_token or not user_id_zepp:
            cursor.execute(
                """
                INSERT INTO step_history (user_id, account_id, step_value, is_random, is_batch, result, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    request.db_user_id,
                    account_id,
                    actual_step,
                    is_random,
                    1,
                    "fail",
                    "账号未认证",
                ),
            )
            conn.commit()
            results.append(
                {"accountId": account_id, "result": "fail", "error": "账号未完成认证"}
            )
            continue

        ok, msg = post_fake_brand_data(actual_step, app_token, user_id_zepp)

        if ok:
            cursor.execute(
                """
                INSERT INTO step_history (user_id, account_id, step_value, is_random, is_batch, result, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    request.db_user_id,
                    account_id,
                    actual_step,
                    is_random,
                    1,
                    "success",
                    "",
                ),
            )
            conn.commit()
            success_accounts.append(f"{account_user_display}({actual_step}步)")
            results.append(
                {"accountId": account_id, "result": "success", "step": actual_step}
            )
        else:
            cursor.execute(
                """
                INSERT INTO step_history (user_id, account_id, step_value, is_random, is_batch, result, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    request.db_user_id,
                    account_id,
                    actual_step,
                    is_random,
                    1,
                    "fail",
                    msg,
                ),
            )
            conn.commit()
            results.append({"accountId": account_id, "result": "fail", "error": msg})

    conn.close()

    success_count = sum(1 for r in results if r["result"] == "success")
    accounts_str = ", ".join(success_accounts) if success_accounts else "无"
    log_operation(
        request.db_user_id,
        get_user_code(request.db_user_id),
        "batch_set_step",
        f"批量修改步数: 成功{success_count}/{len(account_ids)}, 账号: {accounts_str}",
    )

    return jsonify(
        {
            "success": True,
            "results": results,
            "summary": f"成功 {success_count}/{len(account_ids)}",
        }
    )


@app.route("/api/history", methods=["POST"])
@jwt_required
def get_history():
    data = request.json or {}
    page = data.get("page", 1)
    page_size = data.get("pageSize", 20)
    account_id = data.get("accountId")

    try:
        page = validate_int(page, "页码")
        page_size = validate_int(page_size, "每页数量")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    offset = (page - 1) * page_size

    conn = get_db()
    cursor = conn.cursor()

    where_clause = "WHERE h.user_id = ?"
    params = [request.db_user_id]

    if account_id:
        where_clause += " AND h.account_id = ?"
        params.append(account_id)

    cursor.execute(
        f"""
        SELECT h.*, a.user as account_user, u.code as user_code
        FROM step_history h
        LEFT JOIN accounts a ON h.account_id = a.id
        LEFT JOIN users u ON h.user_id = u.id
        {where_clause}
        ORDER BY h.created_at DESC
        LIMIT ? OFFSET ?
    """,
        params + [page_size, offset],
    )

    history = [dict(row) for row in cursor.fetchall()]

    cursor.execute(
        f"SELECT COUNT(*) as total FROM step_history h {where_clause}", params
    )
    total = cursor.fetchone()["total"]

    conn.close()

    return jsonify(
        {"history": history, "total": total, "page": page, "pageSize": page_size}
    )


@app.route("/api/admin/history", methods=["POST"])
@jwt_required
def get_admin_history():
    if not is_admin(request.db_user_id):
        return jsonify({"error": "无权限"}), 403

    data = request.json or {}
    page = data.get("page", 1)
    page_size = data.get("pageSize", 20)
    user_id = data.get("userId")
    account_id = data.get("accountId")

    try:
        page = validate_int(page, "页码")
        page_size = validate_int(page_size, "每页数量")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    offset = (page - 1) * page_size

    conn = get_db()
    cursor = conn.cursor()

    where_clause = "WHERE 1=1"
    params = []

    if user_id:
        where_clause += " AND h.user_id = ?"
        params.append(user_id)

    if account_id:
        where_clause += " AND h.account_id = ?"
        params.append(account_id)

    cursor.execute(
        f"""
        SELECT h.*, a.user as account_user, u.code as user_code
        FROM step_history h
        LEFT JOIN accounts a ON h.account_id = a.id
        LEFT JOIN users u ON h.user_id = u.id
        {where_clause}
        ORDER BY h.created_at DESC
        LIMIT ? OFFSET ?
    """,
        params + [page_size, offset],
    )

    history = [dict(row) for row in cursor.fetchall()]

    cursor.execute(
        f"SELECT COUNT(*) as total FROM step_history h {where_clause}", params
    )
    total = cursor.fetchone()["total"]

    conn.close()

    return jsonify(
        {"history": history, "total": total, "page": page, "pageSize": page_size}
    )


@app.route("/api/admin/logs", methods=["POST"])
@jwt_required
def get_logs():
    if not is_admin(request.db_user_id):
        return jsonify({"error": "无权限"}), 403

    data = request.json or {}
    page = data.get("page", 1)
    page_size = data.get("pageSize", 20)
    action = data.get("action")
    user_id = data.get("userId")
    start_date = data.get("startDate")
    end_date = data.get("endDate")

    try:
        page = validate_int(page, "页码")
        page_size = validate_int(page_size, "每页数量")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    offset = (page - 1) * page_size

    conn = get_db()
    cursor = conn.cursor()

    where_clause = "WHERE 1=1"
    params = []

    if action:
        where_clause += " AND l.action = ?"
        params.append(action)

    if user_id:
        where_clause += " AND l.user_id = ?"
        params.append(user_id)

    if start_date:
        where_clause += " AND DATE(l.created_at) >= ?"
        params.append(start_date)

    if end_date:
        where_clause += " AND DATE(l.created_at) <= ?"
        params.append(end_date)

    cursor.execute(
        f"""
        SELECT l.*, u.code as user_code
        FROM operation_logs l
        LEFT JOIN users u ON l.user_id = u.id
        {where_clause}
        ORDER BY l.created_at DESC
        LIMIT ? OFFSET ?
    """,
        params + [page_size, offset],
    )

    logs = [dict(row) for row in cursor.fetchall()]

    cursor.execute(
        f"SELECT COUNT(*) as total FROM operation_logs l {where_clause}", params
    )
    total = cursor.fetchone()["total"]

    conn.close()

    return jsonify({"logs": logs, "total": total, "page": page, "pageSize": page_size})


@app.route("/api/tasks", methods=["POST"])
@jwt_required
def handle_tasks():
    data = request.json
    action = data.get("action", "list")

    conn = get_db()
    cursor = conn.cursor()

    if action == "list":
        cursor.execute(
            """
            SELECT t.*, a.user as account_user
            FROM scheduled_tasks t
            LEFT JOIN accounts a ON t.account_id = a.id
            WHERE t.user_id = ?
            ORDER BY t.created_at DESC
        """,
            (request.db_user_id,),
        )
        tasks = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify({"tasks": tasks})

    elif action == "create":
        account_id = data.get("accountId")
        task_type = data.get("taskType", "fixed")
        step_value = data.get("stepValue", "").strip()
        execution_time = data.get("executionTime", "08:00").strip()

        if not account_id:
            return jsonify({"error": "请选择账号"}), 400

        if not step_value:
            return jsonify({"error": "请输入步数"}), 400

        if task_type == "fixed":
            if not step_value.isdigit() or int(step_value) <= 0:
                return jsonify({"error": "步数必须大于0"}), 400
        elif task_type == "random":
            if "-" not in step_value:
                return jsonify({"error": "随机步数请输入范围，如：10000-20000"}), 400
            try:
                parts = step_value.split("-")
                min_step = int(parts[0])
                max_step = int(parts[1])
                if min_step <= 0 or max_step <= 0 or min_step >= max_step:
                    return jsonify(
                        {"error": "步数范围最小值必须大于0，且最大值要大于最小值"}
                    ), 400
            except:
                return jsonify({"error": "步数范围格式错误"}), 400

        try:
            account_id = validate_int(account_id, "账号ID")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        cursor.execute(
            "SELECT id FROM accounts WHERE id = ? AND user_id = ?",
            (account_id, request.db_user_id),
        )
        if not cursor.fetchone():
            conn.close()
            return jsonify({"error": "账号不存在"}), 404

        cursor.execute(
            """
            INSERT INTO scheduled_tasks (user_id, account_id, task_type, step_value, execution_time)
            VALUES (?, ?, ?, ?, ?)
        """,
            (request.db_user_id, account_id, task_type, step_value, execution_time),
        )
        conn.commit()
        task_id = cursor.lastrowid
        conn.close()

        log_operation(
            request.db_user_id,
            get_user_code(request.db_user_id),
            "create_task",
            f"创建定时任务: 账号{account_id}, 步数{step_value}, 时间{execution_time}",
        )
        schedule_task(task_id)

        return jsonify({"success": True, "task": {"id": task_id}})

    conn.close()
    return jsonify({"error": "无效操作"}), 400


@app.route("/api/task/update", methods=["POST"])
@jwt_required
def update_task():
    data = request.json
    task_id = data.get("id")
    task_type = data.get("taskType")
    step_value = data.get("stepValue")
    execution_time = data.get("executionTime")

    try:
        task_id = validate_int(task_id, "任务ID")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM scheduled_tasks WHERE id = ? AND user_id = ?",
        (task_id, request.db_user_id),
    )
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "任务不存在"}), 404

    update_fields = []
    params = []

    if task_type:
        update_fields.append("task_type = ?")
        params.append(task_type)

    if step_value:
        update_fields.append("step_value = ?")
        params.append(step_value)

    if execution_time:
        update_fields.append("execution_time = ?")
        params.append(execution_time)

    if not update_fields:
        conn.close()
        return jsonify({"error": "没有要更新的内容"}), 400

    params.append(task_id)
    cursor.execute(
        f"""
        UPDATE scheduled_tasks SET {", ".join(update_fields)}
        WHERE id = ?
    """,
        params,
    )
    conn.commit()
    conn.close()

    reschedule_task(task_id)

    return jsonify({"success": True})


@app.route("/api/task/delete", methods=["POST"])
@jwt_required
def delete_task():
    data = request.json
    task_id = data.get("id")

    try:
        task_id = validate_int(task_id, "任务ID")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM scheduled_tasks WHERE id = ? AND user_id = ?",
        (task_id, request.db_user_id),
    )
    conn.commit()
    log_operation(
        request.db_user_id,
        get_user_code(request.db_user_id),
        "delete_task",
        f"删除定时任务: {task_id}",
    )
    conn.close()

    remove_scheduled_task(task_id)

    return jsonify({"success": True})


@app.route("/api/task/toggle", methods=["POST"])
@jwt_required
def toggle_task():
    data = request.json
    task_id = data.get("id")

    try:
        task_id = validate_int(task_id, "任务ID")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT is_active FROM scheduled_tasks WHERE id = ? AND user_id = ?",
        (task_id, request.db_user_id),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "任务不存在"}), 404

    new_status = 0 if row["is_active"] == 1 else 1
    cursor.execute(
        "UPDATE scheduled_tasks SET is_active = ? WHERE id = ?", (new_status, task_id)
    )
    conn.commit()
    conn.close()

    if new_status == 1:
        schedule_task(task_id)
    else:
        remove_scheduled_task(task_id)

    return jsonify({"success": True, "isActive": new_status})


scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
scheduled_jobs = {}


def execute_scheduled_task(task_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT t.*, a.user, a.password, a.app_token, a.user_id_zepp, a.is_phone, a.device_id
        FROM scheduled_tasks t
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE t.id = ?
    """,
        (task_id,),
    )
    task = cursor.fetchone()

    if not task or task["is_active"] != 1:
        conn.close()
        return

    step_value = task["step_value"]
    task_type = task["task_type"]

    if task_type == "random" and "-" in step_value:
        try:
            parts = step_value.split("-")
            min_step = int(parts[0])
            max_step = int(parts[1])
            step_value = str(random.randint(min_step, max_step))
        except:
            conn.close()
            return

    app_token = task["app_token"]
    user_id_zepp = task["user_id_zepp"]
    user = task["user"]
    password = task["password"]
    is_phone = bool(task["is_phone"])

    if not app_token or not user_id_zepp:
        cursor.execute(
            """
            INSERT INTO step_history (user_id, account_id, step_value, is_random, is_batch, result, error_msg)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                task["user_id"],
                task["account_id"],
                step_value,
                1 if task_type == "random" else 0,
                0,
                "fail",
                "账号未认证",
            ),
        )
        conn.commit()
        conn.close()
        return

    ok, msg = post_fake_brand_data(step_value, app_token, user_id_zepp)

    if not ok:
        device_id = secrets.token_hex(8)
        access_token, msg = login_access_token(user, password)
        if access_token:
            login_token, new_app_token, new_user_id_zepp, msg = grant_login_tokens(
                access_token, device_id, is_phone
            )
            if login_token:
                cursor.execute(
                    """
                    UPDATE accounts SET app_token = ?, user_id_zepp = ?, device_id = ?, updated_at = ?
                    WHERE id = ?
                """,
                    (
                        new_app_token,
                        new_user_id_zepp,
                        device_id,
                        get_beijing_now().isoformat(),
                        task["account_id"],
                    ),
                )
                conn.commit()

                ok, msg = post_fake_brand_data(
                    step_value, new_app_token, new_user_id_zepp
                )
                if ok:
                    app_token = new_app_token
                    user_id_zepp = new_user_id_zepp

    cursor.execute(
        """
        INSERT INTO step_history (user_id, account_id, step_value, is_random, is_batch, result, error_msg)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            task["user_id"],
            task["account_id"],
            step_value,
            1 if task_type == "random" else 0,
            0,
            "success" if ok else "fail",
            msg,
        ),
    )
    conn.commit()

    cursor.execute(
        "UPDATE scheduled_tasks SET last_run_at = ? WHERE id = ?",
        (get_beijing_now().isoformat(), task_id),
    )
    conn.commit()
    conn.close()


def schedule_task(task_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT execution_time, is_active FROM scheduled_tasks WHERE id = ?", (task_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row or row["is_active"] != 1:
        return

    execution_time = row["execution_time"]
    hour, minute = map(int, execution_time.split(":"))

    job_id = f"task_{task_id}"

    if job_id in scheduled_jobs:
        remove_scheduled_task(task_id)

    scheduler.add_job(
        func=execute_scheduled_task,
        trigger="cron",
        hour=hour,
        minute=minute,
        args=[task_id],
        id=job_id,
        replace_existing=True,
    )
    scheduled_jobs[job_id] = task_id


def reschedule_task(task_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT is_active FROM scheduled_tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()

    if row and row["is_active"] == 1:
        schedule_task(task_id)
    else:
        remove_scheduled_task(task_id)


def remove_scheduled_task(task_id):
    job_id = f"task_{task_id}"
    if job_id in scheduled_jobs:
        scheduler.remove_job(job_id)
        del scheduled_jobs[job_id]


def init_scheduled_tasks():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM scheduled_tasks WHERE is_active = 1")
    tasks = cursor.fetchall()
    conn.close()

    for task in tasks:
        schedule_task(task["id"])


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


if __name__ == "__main__":
    init_scheduled_tasks()
    scheduler.start()
    app.run(host="0.0.0.0", port=50000, debug=True)
