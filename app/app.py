from flask import Flask, jsonify
import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

app = Flask(__name__)

# PostgreSQL подключение
def get_db():
    """Простое подключение к БД"""
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'postgres-service'),
            dbname=os.getenv('POSTGRES_DB', 'ip_lookup_db'),
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', 'postgres'),
            port=5434
        )
        return conn
    except Exception as e:
        print(f"DB error: {e}")
        return None

# Создаём таблицу при старте(дебаг)
def init_db():
    print('Привет я принт')
    conn = get_db()
    if not conn:
        return
    print('Привет я принт 2')
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ip_history (
                    id SERIAL PRIMARY KEY,
                    ip VARCHAR(45),
                    provider VARCHAR(50),
                    timestamp TIMESTAMP DEFAULT NOW()
                )
            """)
            conn.commit()
        print("Database table created")
    except Exception as e:
        print(f"DB init error: {e}")

    finally:
        print('Привет я принт 3')
        conn.close()

#  Провайдеры абстрактно 
class IPProvider(ABC):
    @abstractmethod
    def get_ip(self) -> str:
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass

class IpApiProvider(IPProvider):
    @property
    def name(self):
        return "ip-api.com"
    
    def get_ip(self):
        try:
            response = requests.get('http://ip-api.com/json/')
            data = response.json()
            ip = data.get('query')
            return ip
        except:
            return None

class JsonIpProvider(IPProvider):
    @property
    def name(self):
        return "jsonip.com"
    
    def get_ip(self):
        try:
            response = requests.get('https://jsonip.com/')
            data = response.json()
            return data.get('ip')
        except:
            return None

def save_ip_to_db(ip, provider):
    """Сохраняем IP в PostgreSQL"""
    if not ip:
        return
    
    conn = get_db()
    if not conn:
        return
    
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ip_history (ip, provider) VALUES (%s, %s)",
                (ip, provider)
            )
            conn.commit()
        print(f"Saved to DB: {ip}")
    except Exception as e:
        print(f"DB save error: {e}")
    finally:
        conn.close()


PROVIDERS = {
    'ipapi': IpApiProvider(),
    'jsonip': JsonIpProvider()
}

@app.route('/')
def index():
    return '''
    <h1>IP Lookup</h1>
    <p><a href="/ip">Get IP</a></p>
    <p><a href="/history">View history</a></p>
    '''

@app.route('/ip')
def get_ip():
    provider_name = os.getenv('TYPE', 'jsonip')
    provider = PROVIDERS.get(provider_name)
    
    if not provider:
        return jsonify({"error": "Provider not found"}), 404
    
    ip = provider.get_ip()
    
    if ip:
        # Сохраняем в БД
        save_ip_to_db(ip, provider.name)
        
        # Сохраняем в файл
        data_dir = Path("/app/data")
        data_dir.mkdir(exist_ok=True)
        result_file = data_dir / f"ip_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(result_file, 'w') as f:
            import json
            json.dump({"ip": ip, "provider": provider.name}, f, indent=2)
        
        return jsonify({
            "myIP": ip,
            "provider": provider.name,
            "saved_to": "PostgreSQL + file"
        })
    
    return jsonify({"error": "Failed to get IP"}), 500

@app.route('/history')
def history():
    """Показываем историю из БД"""
    conn = get_db()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM ip_history ORDER BY timestamp DESC LIMIT 20")
            records = cur.fetchall()

            for record in records:
                if 'timestamp' in record:
                    record['timestamp'] = record['timestamp'].isoformat()
            
            return jsonify({
                "count": len(records),
                "history": records
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/health')
def health():
    """Простая проверка здоровья"""
    db_ok = bool(get_db())
    return jsonify({
        "status": "ok",
        "database": "connected" if db_ok else "disconnected",
        "timestamp": datetime.now().isoformat()
    })


if __name__ == "__main__":
    # Инициализируем БД при старте
    init_db()
    
    port = int(os.getenv('PORT', 8000))

    app.run(host='0.0.0.0', port=port, debug=False)
