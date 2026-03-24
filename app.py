import os
import json
import random
import string
import requests
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import current_user, login_user, logout_user, login_required, LoginManager

from config import Config
from models import db, User, Message, ChatMessage, GameRoom

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Iltimos, avval tizimga kiring!"
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()
    # Create admin if not exists
    admin = User.query.filter_by(username='Admin').first()
    if not admin:
        admin = User(
            username='Admin',
            password=generate_password_hash('Abboud2012'),
            display_name='Admin',
            is_admin=True,
            avatar_color='#e74c3c'
        )
        db.session.add(admin)
        db.session.commit()

# ─── GROQ AI HELPER ───
def ask_groq(messages, system_prompt=None):
    """Send messages to Groq API and get response"""
    api_key = app.config['GROQ_API_KEY']
    model = app.config['GROQ_MODEL']
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)
    
    data = {
        "model": model,
        "messages": full_messages,
        "temperature": 0.7,
        "max_tokens": 2048
    }
    
    try:
        resp = requests.post('https://api.groq.com/openai/v1/chat/completions', 
                           headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"Xatolik yuz berdi: {str(e)}"

# ─── AUTH ROUTES ───
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        
        if len(username) < 3:
            flash("Username kamida 3 ta belgidan iborat bo'lishi kerak!", 'danger')
            return render_template('signup.html')
        if len(password) < 4:
            flash("Parol kamida 4 ta belgidan iborat bo'lishi kerak!", 'danger')
            return render_template('signup.html')
        if password != password2:
            flash("Parollar mos kelmadi!", 'danger')
            return render_template('signup.html')
        if User.query.filter_by(username=username).first():
            flash("Bu username allaqachon band!", 'danger')
            return render_template('signup.html')
        
        colors = ['#6C5CE7', '#00B894', '#E17055', '#0984E3', '#D63031', '#E84393', '#00CEC9', '#FDCB6E']
        user = User(
            username=username,
            password=generate_password_hash(password),
            display_name=username,
            avatar_color=random.choice(colors)
        )
        db.session.add(user)
        db.session.commit()
        flash("Akkaunt yaratildi! Endi kirishingiz mumkin.", 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            user.is_online = True
            db.session.commit()
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash("Login muvaffaqiyatsiz. Username yoki parolni tekshiring.", 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    if current_user.is_authenticated:
        current_user.is_online = False
        db.session.commit()
    logout_user()
    return redirect(url_for('index'))

# ─── DASHBOARD ───
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

# ─── AI CHATBOT ───
@app.route('/chat')
@login_required
def chat():
    messages = ChatMessage.query.filter_by(user_id=current_user.id).order_by(ChatMessage.timestamp.asc()).all()
    return render_template('chat.html', messages=messages)

@app.route('/chat/send', methods=['POST'])
@login_required
def chat_send():
    data = request.get_json()
    user_msg = data.get('message', '').strip()
    if not user_msg:
        return jsonify({'error': 'Xabar bo\'sh'}), 400
    
    # Save user message
    cm = ChatMessage(user_id=current_user.id, role='user', content=user_msg)
    db.session.add(cm)
    db.session.commit()
    
    # Get recent context
    recent = ChatMessage.query.filter_by(user_id=current_user.id).order_by(ChatMessage.timestamp.desc()).limit(10).all()
    recent.reverse()
    msgs = [{"role": m.role, "content": m.content} for m in recent]
    
    system = """Sen o'zbekcha gapiradigan AI yordamchisan. Sening isming EduBot. 
    Sen doimo o'zbek tilida javob berasan. Sen do'stona, aqlli va yordam berishga tayyorsan.
    Javoblaringni aniq va tushunarli qilib yoz. Agar kerak bo'lsa, emoji ishlat."""
    
    reply = ask_groq(msgs, system)
    
    # Save assistant message
    am = ChatMessage(user_id=current_user.id, role='assistant', content=reply)
    db.session.add(am)
    db.session.commit()
    
    return jsonify({'reply': reply})

@app.route('/chat/clear', methods=['POST'])
@login_required
def chat_clear():
    ChatMessage.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'status': 'ok'})

# ─── MESSENGER ───
@app.route('/messenger')
@login_required
def messenger():
    users = User.query.filter(User.id != current_user.id).all()
    return render_template('messenger.html', users=users)

@app.route('/messenger/<int:user_id>')
@login_required
def messenger_chat(user_id):
    other = User.query.get_or_404(user_id)
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()
    
    # Mark as read
    Message.query.filter_by(sender_id=user_id, receiver_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    
    users = User.query.filter(User.id != current_user.id).all()
    return render_template('messenger.html', users=users, other=other, messages=messages)

@app.route('/messenger/send', methods=['POST'])
@login_required
def messenger_send():
    data = request.get_json()
    receiver_id = data.get('receiver_id')
    content = data.get('message', '').strip()
    if not content or not receiver_id:
        return jsonify({'error': 'Bo\'sh'}), 400
    
    msg = Message(sender_id=current_user.id, receiver_id=receiver_id, content=content)
    db.session.add(msg)
    db.session.commit()
    return jsonify({'status': 'ok', 'timestamp': msg.timestamp.strftime('%H:%M')})

@app.route('/messenger/poll/<int:user_id>')
@login_required
def messenger_poll(user_id):
    last_id = request.args.get('last_id', 0, type=int)
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).filter(Message.id > last_id).order_by(Message.timestamp.asc()).all()
    
    result = []
    for m in messages:
        result.append({
            'id': m.id,
            'sender_id': m.sender_id,
            'content': m.content,
            'timestamp': m.timestamp.strftime('%H:%M'),
            'is_mine': m.sender_id == current_user.id
        })
    return jsonify(result)

# ─── SPEED TYPE ───
@app.route('/speedtype')
@login_required
def speedtype():
    return render_template('speedtype.html')

@app.route('/speedtype/generate', methods=['POST'])
@login_required
def speedtype_generate():
    data = request.get_json()
    difficulty = data.get('difficulty', 'oson')
    
    prompts = {
        'oson': "O'zbek tilida 30-40 so'zdan iborat oddiy matn yoz. Bolalar uchun tushunarli bo'lsin. Faqat matnni yoz, boshqa narsa yozma.",
        'o\'rta': "O'zbek tilida 40-60 so'zdan iborat o'rtacha qiyinlikdagi matn yoz. Ilmiy yoki tarixiy mavzuda. Faqat matnni yoz.",
        'qiyin': "O'zbek tilida 60-80 so'zdan iborat murakkab ilmiy matn yoz. Professional atamalar ishlat. Faqat matnni yoz."
    }
    
    prompt = prompts.get(difficulty, prompts['oson'])
    text = ask_groq([{"role": "user", "content": prompt}], 
                    "Sen matn generatori san. Faqat so'ralgan matnni yoz, boshqa hech narsa yozma.")
    return jsonify({'text': text})

@app.route('/speedtype/save', methods=['POST'])
@login_required
def speedtype_save():
    data = request.get_json()
    wpm = data.get('wpm', 0)
    if wpm > current_user.typing_best_wpm:
        current_user.typing_best_wpm = wpm
        current_user.total_score += 5
        db.session.commit()
    return jsonify({'best': current_user.typing_best_wpm})

# ─── HOMEWORK HELPER ───
@app.route('/homework')
@login_required
def homework():
    return render_template('homework.html')

@app.route('/homework/ask', methods=['POST'])
@login_required
def homework_ask():
    data = request.get_json()
    question = data.get('question', '')
    subject = data.get('subject', 'umumiy')
    
    system = f"""Sen {subject} fanidan professional o'qituvchisan. O'zbek tilida javob berasan.
    Talabaga vazifani tushuntir, qadam-baqadam yechimini ko'rsat. 
    Formulalar va misollar keltir. Javobni tushunarli va batafsil yoz."""
    
    reply = ask_groq([{"role": "user", "content": question}], system)
    return jsonify({'answer': reply})

# ─── TEST GENERATOR ───
@app.route('/testgen')
@login_required
def testgen():
    return render_template('testgen.html')

@app.route('/testgen/generate', methods=['POST'])
@login_required
def testgen_generate():
    data = request.get_json()
    topic = data.get('topic', '')
    count = min(data.get('count', 5), 20)
    
    system = """Sen test yaratuvchi AIsan. O'zbek tilida test savollarini yaratasan.
    Har bir savol uchun 4 ta variant (A, B, C, D) va to'g'ri javobni ko'rsat.
    Javobni FAQAT quyidagi JSON formatda ber, boshqa hech narsa yozma:
    [{"question": "Savol matni", "options": {"A": "variant1", "B": "variant2", "C": "variant3", "D": "variant4"}, "correct": "A"}]"""
    
    prompt = f"'{topic}' mavzusida {count} ta test savoli yarat. JSON formatda ber."
    reply = ask_groq([{"role": "user", "content": prompt}], system)
    
    # Try to parse JSON from reply
    try:
        # Find JSON in reply
        start = reply.find('[')
        end = reply.rfind(']') + 1
        if start >= 0 and end > start:
            questions = json.loads(reply[start:end])
        else:
            questions = json.loads(reply)
        return jsonify({'questions': questions})
    except:
        return jsonify({'error': 'Test yaratishda xatolik. Qaytadan urinib ko\'ring.', 'raw': reply}), 400

# ─── KONSPEKT ───
@app.route('/konspekt')
@login_required
def konspekt():
    return render_template('konspekt.html')

@app.route('/konspekt/generate', methods=['POST'])
@login_required
def konspekt_generate():
    data = request.get_json()
    topic = data.get('topic', '')
    style = data.get('style', 'batafsil')
    
    styles = {
        'batafsil': "Batafsil konspekt yoz, har bir bo'limni chuqur tushuntir.",
        'qisqa': "Qisqa va lo'nda konspekt yoz, faqat asosiy fikrlarni yoz.",
        'sxema': "Sxema shaklida konspekt yoz, nuqtalar va bo'limlar bilan."
    }
    
    system = f"""Sen professional konspekt yozuvchi AIsan. O'zbek tilida konspekt yozasan.
    {styles.get(style, styles['batafsil'])}
    Sarlavhalar, bo'limlar, asosiy tushunchalar va xulosalar bilan yoz.
    Markdown formatda yoz."""
    
    reply = ask_groq([{"role": "user", "content": f"'{topic}' mavzusida konspekt yoz."}], system)
    return jsonify({'konspekt': reply})

# ─── TIC TAC TOE ───
@app.route('/tictactoe')
@login_required
def tictactoe():
    return render_template('tictactoe.html')

@app.route('/tictactoe/bot-move', methods=['POST'])
@login_required
def tictactoe_bot_move():
    data = request.get_json()
    board = data.get('board', ['']*9)
    
    # Simple minimax-like AI
    def check_winner(b):
        wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
        for a,bb,c in wins:
            if b[a] == b[bb] == b[c] and b[a] != '':
                return b[a]
        return None
    
    def minimax(b, is_max):
        w = check_winner(b)
        if w == 'O': return 1
        if w == 'X': return -1
        if '' not in b: return 0
        
        if is_max:
            best = -2
            for i in range(9):
                if b[i] == '':
                    b[i] = 'O'
                    best = max(best, minimax(b, False))
                    b[i] = ''
            return best
        else:
            best = 2
            for i in range(9):
                if b[i] == '':
                    b[i] = 'X'
                    best = min(best, minimax(b, True))
                    b[i] = ''
            return best
    
    best_move = -1
    best_score = -2
    for i in range(9):
        if board[i] == '':
            board[i] = 'O'
            score = minimax(board, False)
            board[i] = ''
            if score > best_score:
                best_score = score
                best_move = i
    
    return jsonify({'move': best_move})

@app.route('/tictactoe/save', methods=['POST'])
@login_required
def tictactoe_save():
    data = request.get_json()
    result = data.get('result')  # 'win', 'lose', 'draw'
    if result == 'win':
        current_user.tictactoe_wins += 1
        current_user.total_score += 10
    elif result == 'lose':
        current_user.tictactoe_losses += 1
    db.session.commit()
    return jsonify({'wins': current_user.tictactoe_wins, 'losses': current_user.tictactoe_losses})

# ─── MULTIPLAYER TIC TAC TOE ───
@app.route('/tictactoe/online')
@login_required
def tictactoe_online():
    return render_template('tictactoe_online.html')

@app.route('/tictactoe/create-room', methods=['POST'])
@login_required
def tictactoe_create_room():
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    room = GameRoom(
        room_code=code,
        game_type='tictactoe',
        player1_id=current_user.id,
        state=json.dumps({'board': ['']*9, 'turn': 'X'}),
        status='waiting'
    )
    db.session.add(room)
    db.session.commit()
    return jsonify({'room_code': code})

@app.route('/tictactoe/join-room', methods=['POST'])
@login_required
def tictactoe_join_room():
    data = request.get_json()
    code = data.get('code', '').upper()
    room = GameRoom.query.filter_by(room_code=code, game_type='tictactoe', status='waiting').first()
    if not room:
        return jsonify({'error': 'Xona topilmadi yoki to\'lgan'}), 404
    if room.player1_id == current_user.id:
        return jsonify({'error': 'O\'z xonangizga qo\'shila olmaysiz'}), 400
    room.player2_id = current_user.id
    room.status = 'playing'
    db.session.commit()
    return jsonify({'room_code': code})

@app.route('/tictactoe/room/<code>')
@login_required
def tictactoe_room(code):
    room = GameRoom.query.filter_by(room_code=code, game_type='tictactoe').first_or_404()
    return render_template('tictactoe_room.html', room=room)

@app.route('/tictactoe/room-state/<code>')
@login_required
def tictactoe_room_state(code):
    room = GameRoom.query.filter_by(room_code=code, game_type='tictactoe').first_or_404()
    state = json.loads(room.state)
    return jsonify({
        'state': state,
        'status': room.status,
        'player1': room.player1_id,
        'player2': room.player2_id,
        'winner': room.winner_id,
        'my_id': current_user.id,
        'p1_name': User.query.get(room.player1_id).username if room.player1_id else None,
        'p2_name': User.query.get(room.player2_id).username if room.player2_id else None,
    })

@app.route('/tictactoe/room-move/<code>', methods=['POST'])
@login_required
def tictactoe_room_move(code):
    room = GameRoom.query.filter_by(room_code=code, game_type='tictactoe', status='playing').first_or_404()
    data = request.get_json()
    pos = data.get('position')
    state = json.loads(room.state)
    board = state['board']
    turn = state['turn']
    
    # Validate turn
    if turn == 'X' and current_user.id != room.player1_id:
        return jsonify({'error': 'Sizning navbatingiz emas'}), 400
    if turn == 'O' and current_user.id != room.player2_id:
        return jsonify({'error': 'Sizning navbatingiz emas'}), 400
    if board[pos] != '':
        return jsonify({'error': 'Bu joy band'}), 400
    
    board[pos] = turn
    
    # Check winner
    wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    winner = None
    for a,b,c in wins:
        if board[a] == board[b] == board[c] and board[a] != '':
            winner = board[a]
            break
    
    if winner:
        room.status = 'finished'
        winner_id = room.player1_id if winner == 'X' else room.player2_id
        loser_id = room.player2_id if winner == 'X' else room.player1_id
        room.winner_id = winner_id
        w = User.query.get(winner_id)
        l = User.query.get(loser_id)
        if w: w.tictactoe_wins += 1; w.total_score += 10
        if l: l.tictactoe_losses += 1
    elif '' not in board:
        room.status = 'finished'
    
    state['turn'] = 'O' if turn == 'X' else 'X'
    state['board'] = board
    room.state = json.dumps(state)
    db.session.commit()
    
    return jsonify({'status': 'ok'})

# ─── TEST BATTLE ───
@app.route('/testbattle')
@login_required
def testbattle():
    return render_template('testbattle.html')

@app.route('/testbattle/create', methods=['POST'])
@login_required
def testbattle_create():
    data = request.get_json()
    topic = data.get('topic', 'Umumiy bilim')
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    # Generate questions via AI
    system = """Sen test yaratuvchi AIsan. O'zbek tilida 10 ta test savoli yarat.
    Har bir savol uchun 4 ta variant va to'g'ri javobni ko'rsat.
    FAQAT JSON formatda ber:
    [{"question": "Savol", "options": {"A": "v1", "B": "v2", "C": "v3", "D": "v4"}, "correct": "A"}]"""
    
    reply = ask_groq([{"role": "user", "content": f"'{topic}' mavzusida 10 ta test yarat."}], system)
    
    try:
        start = reply.find('[')
        end = reply.rfind(']') + 1
        questions = json.loads(reply[start:end]) if start >= 0 else json.loads(reply)
    except:
        questions = [{"question": f"Savol {i+1}", "options": {"A": "A", "B": "B", "C": "C", "D": "D"}, "correct": "A"} for i in range(10)]
    
    room = GameRoom(
        room_code=code,
        game_type='test_battle',
        player1_id=current_user.id,
        state=json.dumps({'questions': questions, 'p1_score': 0, 'p2_score': 0, 'p1_answers': {}, 'p2_answers': {}, 'p1_done': False, 'p2_done': False}),
        status='waiting'
    )
    db.session.add(room)
    db.session.commit()
    return jsonify({'room_code': code})

@app.route('/testbattle/join', methods=['POST'])
@login_required
def testbattle_join():
    data = request.get_json()
    code = data.get('code', '').upper()
    room = GameRoom.query.filter_by(room_code=code, game_type='test_battle', status='waiting').first()
    if not room:
        return jsonify({'error': 'Xona topilmadi'}), 404
    if room.player1_id == current_user.id:
        return jsonify({'error': 'O\'z xonangizga qo\'shila olmaysiz'}), 400
    room.player2_id = current_user.id
    room.status = 'playing'
    db.session.commit()
    return jsonify({'room_code': code})

@app.route('/testbattle/room/<code>')
@login_required
def testbattle_room(code):
    room = GameRoom.query.filter_by(room_code=code, game_type='test_battle').first_or_404()
    return render_template('testbattle_room.html', room=room)

@app.route('/testbattle/room-state/<code>')
@login_required
def testbattle_room_state(code):
    room = GameRoom.query.filter_by(room_code=code, game_type='test_battle').first_or_404()
    state = json.loads(room.state)
    is_p1 = current_user.id == room.player1_id
    return jsonify({
        'status': room.status,
        'questions': state['questions'],
        'my_score': state['p1_score'] if is_p1 else state['p2_score'],
        'opp_score': state['p2_score'] if is_p1 else state['p1_score'],
        'my_done': state['p1_done'] if is_p1 else state['p2_done'],
        'opp_done': state['p2_done'] if is_p1 else state['p1_done'],
        'winner': room.winner_id,
        'my_id': current_user.id,
        'p1_name': User.query.get(room.player1_id).username if room.player1_id else '',
        'p2_name': User.query.get(room.player2_id).username if room.player2_id else '',
    })

@app.route('/testbattle/answer/<code>', methods=['POST'])
@login_required
def testbattle_answer(code):
    room = GameRoom.query.filter_by(room_code=code, game_type='test_battle', status='playing').first_or_404()
    data = request.get_json()
    answers = data.get('answers', {})
    state = json.loads(room.state)
    questions = state['questions']
    is_p1 = current_user.id == room.player1_id
    
    score = 0
    for i, q in enumerate(questions):
        if answers.get(str(i)) == q['correct']:
            score += 1
    
    if is_p1:
        state['p1_score'] = score
        state['p1_done'] = True
        state['p1_answers'] = answers
    else:
        state['p2_score'] = score
        state['p2_done'] = True
        state['p2_answers'] = answers
    
    # Check if both done
    if state['p1_done'] and state['p2_done']:
        room.status = 'finished'
        if state['p1_score'] > state['p2_score']:
            room.winner_id = room.player1_id
            w = User.query.get(room.player1_id); w.test_wins += 1; w.total_score += 15
            l = User.query.get(room.player2_id); l.test_losses += 1
        elif state['p2_score'] > state['p1_score']:
            room.winner_id = room.player2_id
            w = User.query.get(room.player2_id); w.test_wins += 1; w.total_score += 15
            l = User.query.get(room.player1_id); l.test_losses += 1
    
    room.state = json.dumps(state)
    db.session.commit()
    return jsonify({'score': score})

# ─── LEADERBOARD ───
@app.route('/leaderboard')
@login_required
def leaderboard():
    users = User.query.order_by(User.total_score.desc()).limit(50).all()
    return render_template('leaderboard.html', users=users)

# ─── ADMIN PANEL ───
@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash("Sizda admin huquqi yo'q!", 'danger')
        return redirect(url_for('dashboard'))
    users = User.query.all()
    messages_count = Message.query.count()
    rooms = GameRoom.query.all()
    return render_template('admin.html', users=users, messages_count=messages_count, rooms=rooms)

@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Ruxsat yo\'q'}), 403
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        return jsonify({'error': 'Adminni o\'chirish mumkin emas'}), 400
    Message.query.filter((Message.sender_id == user_id) | (Message.receiver_id == user_id)).delete()
    ChatMessage.query.filter_by(user_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/admin/toggle-admin/<int:user_id>', methods=['POST'])
@login_required
def admin_toggle_admin(user_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Ruxsat yo\'q'}), 403
    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    return jsonify({'is_admin': user.is_admin})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
