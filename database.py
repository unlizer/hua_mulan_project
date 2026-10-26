import sqlite3
from werkzeug.security import generate_password_hash

DB_NAME = "hua_mulan_auth_schedule.db"

def init_db():
    """Инициализация базы данных и заполнение начальными справочниками."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS schedule")
        cursor.execute("DROP TABLE IF EXISTS employees")
        cursor.execute("DROP TABLE IF EXISTS roles")
        cursor.execute("DROP TABLE IF EXISTS shift_types")

        # Создание таблиц
        cursor.execute("CREATE TABLE roles (id INTEGER PRIMARY KEY, name TEXT UNIQUE, is_admin BOOLEAN)")
        cursor.execute("CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT, login TEXT UNIQUE, password_hash TEXT, role_id INTEGER, FOREIGN KEY(role_id) REFERENCES roles(id))")
        cursor.execute("CREATE TABLE shift_types (id INTEGER PRIMARY KEY, name TEXT, code TEXT UNIQUE)")
        cursor.execute("CREATE TABLE schedule (id INTEGER PRIMARY KEY, emp_id INTEGER, date TEXT, shift_id INTEGER, UNIQUE(emp_id, date))")
        
        # Справочник должностей
        cursor.executemany("INSERT INTO roles (id, name, is_admin) VALUES (?, ?, ?)", [
            (1, 'Администратор', True), 
            (2, 'Повар', False), 
            (3, 'Официант', False)
        ])
        
        # ИСПРАВЛЕНО: коды смен теперь строго соответствуют 'У' и 'В'
        cursor.executemany("INSERT INTO shift_types (id, name, code) VALUES (?, ?, ?)", [
            (1, 'Утро (10:00 - 23:00)', 'У'), 
            (2, 'Вечер (16:30 - 23:00)', 'В'), 
            (3, 'Выходной', 'ВЫХ')
        ])
        
        # Генерация дефолтных паролей для старта
        default_password = generate_password_hash("mulan2026")
        
        # Начальный штат сотрудников
        cursor.executemany("INSERT INTO employees (id, name, login, password_hash, role_id) VALUES (?, ?, ?, ?, ?)", [
            (1, 'Иван Иванов', 'ivanov', default_password, 1),
            (2, 'Светлана Цыренова', 'tsyrenova', default_password, 3),
            (3, 'Дмитрий Ли', 'lee', default_password, 2)
        ])
        conn.commit()

if __name__ == '__main__':
    init_db()
    print("База данных успешно пересоздана и инициализирована с кодами У и В.")
