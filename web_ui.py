# -*- coding: utf-8 -*-
from flask import Flask, render_template_string, jsonify, request
from flask_cors import CORS
import threading
import psutil
import os
import time
import json

app = Flask(__name__)
CORS(app)

# Глобальная переменная для доступа к Мии
mia_instance = None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Мия - Панель управления</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { 
            text-align: center; 
            color: #e94560; 
            margin-bottom: 30px;
            font-size: 2em;
        }
        .card {
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #0f3460;
        }
        .card h2 {
            color: #e94560;
            margin-bottom: 15px;
            font-size: 1.2em;
        }
        .status-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #0f3460;
        }
        .status-row:last-child { border-bottom: none; }
        .label { color: #aaa; }
        .value { color: #fff; font-weight: bold; }
        
        .input-group {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }
        input {
            flex: 1;
            padding: 10px;
            background: #0f3460;
            border: 1px solid #e94560;
            border-radius: 5px;
            color: #fff;
            font-size: 1em;
        }
        button {
            padding: 10px 20px;
            background: #e94560;
            border: none;
            border-radius: 5px;
            color: #fff;
            font-size: 1em;
            cursor: pointer;
            transition: background 0.3s;
        }
        button:hover { background: #c23152; }
        
        .log {
            margin-top: 15px;
            max-height: 300px;
            overflow-y: auto;
            background: #0f3460;
            padding: 10px;
            border-radius: 5px;
            font-size: 0.9em;
        }
        .log-entry { padding: 3px 0; color: #aaa; }
        .log-entry.user { color: #e94560; }
        .log-entry.mia { color: #4ecca3; }
        
        .status-dot {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status-dot.online { background: #4ecca3; }
        .status-dot.offline { background: #e94560; }
        
        .voice-btn {
            width: 100%;
            padding: 15px;
            font-size: 1.2em;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Мия — Панель управления</h1>
        
        <div class="card">
            <h2>📊 Статус системы</h2>
            <div class="status-row">
                <span class="label">Мия:</span>
                <span class="value"><span class="status-dot online" id="mia-dot"></span><span id="mia-status">Онлайн</span></span>
            </div>
            <div class="status-row">
                <span class="label">Процессор:</span>
                <span class="value" id="cpu">Загрузка...</span>
            </div>
            <div class="status-row">
                <span class="label">Память:</span>
                <span class="value" id="ram">Загрузка...</span>
            </div>
            <div class="status-row">
                <span class="label">Батарея:</span>
                <span class="value" id="battery">Загрузка...</span>
            </div>
        </div>
        
        <div class="card">
            <h2>💬 Голосовая команда (текст)</h2>
            <div class="input-group">
                <input type="text" id="command" placeholder="Введите команду (например: погода, комплимент, открой ютуб)..." onkeypress="if(event.key==='Enter')sendCommand()">
                <button onclick="sendCommand()">Отправить</button>
            </div>
        </div>
        
        <div class="card">
            <h2>📝 История диалога</h2>
            <div class="log" id="log">
                <div class="log-entry mia">🤖 Мия запущена и готова к работе</div>
            </div>
        </div>
    </div>
    
    <script>
        async function updateStatus() {
            try {
                const resp = await fetch('/api/status');
                const data = await resp.json();
                document.getElementById('cpu').textContent = data.cpu + '%';
                document.getElementById('ram').textContent = data.ram + '%';
                document.getElementById('battery').textContent = data.battery + '%';
                document.getElementById('disk').textContent = data.disk + '%';
                
                if (data.mia_online) {
                    document.getElementById('mia-dot').className = 'status-dot online';
                    document.getElementById('mia-status').textContent = 'Онлайн';
                } else {
                    document.getElementById('mia-dot').className = 'status-dot offline';
                    document.getElementById('mia-status').textContent = 'Офлайн';
                }
            } catch(e) {}
        }
        
        async function sendCommand() {
            const input = document.getElementById('command');
            const cmd = input.value.trim();
            if (!cmd) return;
            
            addLog(cmd, 'user');
            
            try {
                const resp = await fetch('/api/command', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({command: cmd})
                });
                const data = await resp.json();
                addLog(data.response, 'mia');
            } catch(e) {
                addLog('Ошибка связи с Мией', 'mia');
            }
            
            input.value = '';
            scrollLog();
        }
        
        function addLog(text, type) {
            const icon = type === 'user' ? '👤' : '🤖';
            const entry = document.createElement('div');
            entry.className = 'log-entry ' + type;
            entry.textContent = icon + ' ' + text;
            document.getElementById('log').appendChild(entry);
        }
        
        function scrollLog() {
            const log = document.getElementById('log');
            log.scrollTop = log.scrollHeight;
        }
        
        setInterval(updateStatus, 2000);
        updateStatus();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/status')
def api_status():
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory().percent
    battery = psutil.sensors_battery()
    bat_percent = battery.percent if battery else 100

    
    return jsonify({
        "cpu": cpu,
        "ram": ram,
        "battery": bat_percent,
        "mia_online": mia_instance is not None
    })

@app.route('/api/command', methods=['POST'])
def api_command():
    data = request.json
    command = data.get('command', '')
    
    if mia_instance:
        try:
            # Передаём команду Мии
            result = mia_instance.process_command(command.lower())
            if result:
                response = "Выполнено ✅"
            else:
                response = "Команда не распознана. Попробуйте: погода, время, открой ютуб, комплимент"
        except Exception as e:
            response = f"Ошибка: {str(e)[:100]}"
    else:
        response = "Мия ещё не запущена. Запустите main.py"
    
    return jsonify({"response": response})

def start_server(port=8080):
    """Запустить веб-сервер"""
    print(f"\n🌐 Web UI запущен: http://127.0.0.1:{port}")
    print(f"   Откройте этот адрес в браузере\n")
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)