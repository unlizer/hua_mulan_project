import sqlite3
import os
import calendar
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from datetime import datetime
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.urandom(24)
DB_NAME = "hua_mulan_auth_schedule.db"

def init_db_internal():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS roles (id INTEGER PRIMARY KEY, name TEXT UNIQUE, is_admin BOOLEAN)")
        cursor.execute("CREATE TABLE IF NOT EXISTS employees (id INTEGER PRIMARY KEY, name TEXT, login TEXT UNIQUE, password_hash TEXT, role_id INTEGER, FOREIGN KEY(role_id) REFERENCES roles(id))")
        cursor.execute("CREATE TABLE IF NOT EXISTS shift_types (id INTEGER PRIMARY KEY, name TEXT, code TEXT UNIQUE)")
        cursor.execute("CREATE TABLE IF NOT EXISTS schedule (id INTEGER PRIMARY KEY, emp_id INTEGER, date TEXT, shift_id INTEGER, UNIQUE(emp_id, date))")
        
        cursor.executemany("INSERT OR IGNORE INTO roles (id, name, is_admin) VALUES (?, ?, ?)", [
            (1, 'Администратор', True), (2, 'Повар', False), (3, 'Официант', False)
        ])
        cursor.executemany("INSERT OR IGNORE INTO shift_types (id, name, code) VALUES (?, ?, ?)", [
            (1, 'Утро (10:00 - 23:00)', 'У'), (2, 'Вечер (16:30 - 23:30)', 'В'), (3, 'Выходной', 'ВЫХ')
        ])
        default_password = generate_password_hash("mulan2026")
        cursor.executemany("INSERT OR IGNORE INTO employees (id, name, login, password_hash, role_id) VALUES (?, ?, ?, ?, ?)", [
            (1, 'Иван Иванов', 'ivanov', default_password, 1),
            (2, 'Светлана Цыренова', 'tsyrenova', default_password, 3),
            (3, 'Дмитрий Ли', 'lee', default_password, 2)
        ])
        conn.commit()

def get_days_in_month(month_str, period):
    year, month = map(int, month_str.split('-'))
    num_days = calendar.monthrange(year, month)[1]
    weekdays_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    
    start_day = 1 if period == "1-15" else 16
    end_day = 15 if period == "1-15" else num_days
    
    result = []
    for day in range(start_day, end_day + 1):
        date_obj = datetime(year, month, day)
        date_str = date_obj.strftime('%Y-%m-%d')
        result.append({
            'date': date_str,
            'day_num': f"{day:02d}",
            'weekday_name': weekdays_ru[date_obj.weekday()],
            'weekday_index': date_obj.weekday()
        })
    return result

@app.route('/')
def index():
    init_db_internal()
    if 'user_id' not in session:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT e.login, e.name, r.name FROM employees e JOIN roles r ON e.role_id = r.id WHERE r.is_admin = 0')
            staff_list = cursor.fetchall()
        return render_template('login.html', staff_list=staff_list)
        
    selected_month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    selected_period = request.args.get('period', '1-15')
    days = get_days_in_month(selected_month, selected_period)
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        # Получаем роли для формы добавления
        cursor.execute("SELECT id, name FROM roles")
        roles = cursor.fetchall()

        cursor.execute('SELECT e.id, e.name, r.name, r.is_admin FROM employees e JOIN roles r ON e.role_id = r.id')
        all_staff = cursor.fetchall()

        cursor.execute('''
            SELECT emp_id, date, st.code 
            FROM schedule s 
            JOIN shift_types st ON s.shift_id = st.id 
            WHERE date LIKE ?
        ''', (f"{selected_month}%",))
        raw_shifts = cursor.fetchall()
        
        shifts_dict = {}
        for emp_id, date, code in raw_shifts:
            if emp_id not in shifts_dict: shifts_dict[emp_id] = {}
            shifts_dict[emp_id][date] = code

        salary_dict = {}
        for emp_id, emp_name, role_name, is_admin in all_staff:
            mornings_in_month = sum(
                1 for date, code in shifts_dict.get(emp_id, {}).items() 
                if code == 'У' and date.startswith(selected_month)
            )
            rate = 250 if is_admin else (180 if mornings_in_month >= 8 else 150)
            
            total_salary = 0
            for d in days:
                code = shifts_dict.get(emp_id, {}).get(d['date'])
                if code == 'У':
                    total_salary += 13 * rate
                elif code == 'В':
                    total_salary += 7 * rate
            salary_dict[emp_id] = total_salary

        grid_data = []
        for emp_id, emp_name, role_name, is_admin in all_staff:
            emp_shifts = []
            for d in days:
                emp_shifts.append({
                    'date': d['date'],
                    'code': shifts_dict.get(emp_id, {}).get(d['date'], '')
                })
            grid_data.append({
                'id': emp_id, 'name': emp_name, 'role': role_name,
                'shifts': emp_shifts, 'salary': salary_dict[emp_id], 'is_admin_role': is_admin
            })

    return render_template('index.html', grid_data=grid_data, days=days, 
                           selected_month=selected_month, selected_period=selected_period, 
                           roles=roles)

@app.route('/update_shift_ajax', methods=['POST'])
def update_shift_ajax():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Сессия истекла, войдите заново'}), 401
        
    data = request.get_json()
    emp_id = int(data.get('emp_id'))
    date = data.get('date')
    code = data.get('code')
    
    if not session.get('is_admin') and session.get('user_id') != emp_id:
        return jsonify({'status': 'error', 'message': 'Вы можете ставить смены только себе!'}), 403
        
    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        weekday = date_obj.weekday() # 0=Пн, ..., 6=Вс
    except Exception:
        return jsonify({'status': 'error', 'message': 'Неверный формат даты'}), 400

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        if code in ['У', 'В']:
            # Проверяем лимиты для других сотрудников на эту дату
            cursor.execute('''
                SELECT s.emp_id, st.code 
                FROM schedule s 
                JOIN shift_types st ON s.shift_id = st.id 
                WHERE s.date = ? AND s.emp_id != ?
            ''', (date, emp_id))
            other_shifts = cursor.fetchall()
            
            count_u = sum(1 for _, c in other_shifts if c == 'У')
            count_v = sum(1 for _, c in other_shifts if c == 'В')
            
            if weekday < 4: # Пн-Чт: макс 1 У и 1 В
                if code == 'У' and count_u >= 1:
                    return jsonify({'status': 'error', 'message': 'С понедельника по четверг разрешен только 1 сотрудник с утра!'}), 400
                if code == 'В' and count_v >= 1:
                    return jsonify({'status': 'error', 'message': 'С понедельника по четверг разрешен только 1 сотрудник с вечера!'}), 400
            else: # Пт-Вс: макс 2 У и 1 В
                if code == 'У' and count_u >= 2:
                    return jsonify({'status': 'error', 'message': 'С пятницы по воскресенье разрешено максимум 2 сотрудника с утра!'}), 400
                if code == 'В' and count_v >= 1:
                    return jsonify({'status': 'error', 'message': 'С пятницы по воскресенье разрешен только 1 сотрудник с вечера!'}), 400

        if code == '' or code == 'ВЫХ':
            cursor.execute("DELETE FROM schedule WHERE emp_id = ? AND date = ?", (emp_id, date))
        else:
            cursor.execute("SELECT id FROM shift_types WHERE code = ?", (code,))
            shift_row = cursor.fetchone()
            if shift_row:
                cursor.execute("INSERT OR REPLACE INTO schedule (emp_id, date, shift_id) VALUES (?, ?, ?)", (emp_id, date, shift_row[0]))
        conn.commit()
        
    return jsonify({'status': 'success'})

@app.route('/delete_employee_ajax', methods=['POST'])
def delete_employee_ajax():
    if not session.get('is_admin'): 
        return jsonify({'status': 'error', 'message': 'Доступ запрещен'}), 403
    data = request.get_json()
    emp_id = data.get('emp_id')
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM schedule WHERE emp_id = ?", (emp_id,))
        cursor.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
        conn.commit()
    return jsonify({'status': 'success'})

@app.route('/login', methods=['POST'])
def login():
    login_input = request.form.get('login').strip().lower()
    password_input = request.form.get('password')
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT e.id, e.name, e.password_hash, r.name, r.is_admin FROM employees e JOIN roles r ON e.role_id = r.id WHERE e.login = ?', (login_input,))
        user = cursor.fetchone()
    if user and check_password_hash(user[2], password_input):
        session['user_id'] = user[0]
        session['user_name'] = user[1]
        session['role_name'] = user[3]
        session['is_admin'] = bool(user[4])
        return redirect(url_for('index'))
    flash('Неверный логин или пароль!')
    return redirect(url_for('index'))

@app.route('/auto_schedule', methods=['POST'])
def auto_schedule():
    if not session.get('is_admin'): return "Доступ запрещен", 403
    period, month_str = request.form.get('period'), request.form.get('month')
    year, month = map(int, month_str.split('-'))
    
    days = get_days_in_month(month_str, period)

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM employees WHERE role_id = 3") 
        waiters = [r[0] for r in cursor.fetchall()]
        if len(waiters) < 3:
            flash("Ошибка: Для авторасчета нужно минимум 3 официанта в базе!")
            return redirect(url_for('index', month=month_str, period=period))
            
        w_idx = 0
        for d in days:
            date_str = d['date']
            weekday = d['weekday_index']
            
            # Сначала очистим смены официантов на этот день
            for w in waiters:
                cursor.execute("DELETE FROM schedule WHERE emp_id = ? AND date = ?", (w, date_str))
                
            if weekday < 4:  # Пн-Чт: 1 У и 1 В
                cursor.execute("INSERT OR REPLACE INTO schedule (emp_id, date, shift_id) VALUES (?, ?, 1)", (waiters[w_idx % len(waiters)], date_str))
                cursor.execute("INSERT OR REPLACE INTO schedule (emp_id, date, shift_id) VALUES (?, ?, 2)", (waiters[(w_idx+1) % len(waiters)], date_str))
                w_idx += 1
            else:  # Пт-Вс: 2 У и 1 В
                cursor.execute("INSERT OR REPLACE INTO schedule (emp_id, date, shift_id) VALUES (?, ?, 1)", (waiters[w_idx % len(waiters)], date_str))
                cursor.execute("INSERT OR REPLACE INTO schedule (emp_id, date, shift_id) VALUES (?, ?, 1)", (waiters[(w_idx+1) % len(waiters)], date_str))
                cursor.execute("INSERT OR REPLACE INTO schedule (emp_id, date, shift_id) VALUES (?, ?, 2)", (waiters[(w_idx+2) % len(waiters)], date_str))
                w_idx += 2
        conn.commit()
    return redirect(url_for('index', month=month_str, period=period))

@app.route('/add_employee', methods=['POST'])
def add_employee():
    if not session.get('is_admin'): return "Доступ запрещен", 403
    name = request.form.get('name').strip()
    login = request.form.get('login').strip().lower()
    password = request.form.get('password').strip()
    role_id = request.form.get('role_id')
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO employees (name, login, password_hash, role_id) VALUES (?, ?, ?, ?)', (name, login, generate_password_hash(password), role_id))
            conn.commit()
        flash(f'Сотрудник {name} успешно добавлен!')
    except sqlite3.IntegrityError:
        flash('Ошибка: Логин уже занят!')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db_internal()
    app.run(debug=True, port=5000)
