from flask import Flask, render_template, request, jsonify, redirect, session
import json
import os
from datetime import datetime
import threading
import pyautogui
import speech_recognition as sr
import time
from googletrans import Translator, LANGUAGES
import cv2
import mediapipe as mp
 
app = Flask(__name__)
app.secret_key = 'hospital_secret_key'

# Global control variables
head_tracking_active = False
voice_control_active = False
blink_detection_active = False

# Initialize MediaPipe Face Mesh
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# User database file
USER_DATA_FILE = "users_data.json"
 
def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        "patients": {
            "john": {"password": "123", "name": "John Smith", "patient_id": "P001", "language": "en"},
            "sarah": {"password": "123", "name": "Sarah Johnson", "patient_id": "P002", "language": "es"},
            "ali": {"password": "123", "name": "Ali Hassan", "patient_id": "P003", "language": "ar"},
            "marie": {"password": "123", "name": "Marie Dubois", "patient_id": "P004", "language": "fr"},
            "multilang": {"password": "123", "name": "Multi Language User", "patient_id": "P005", "language": "en"}
        },
        "doctors": {
            "drsmith": {"password": "123", "name": "Smith", "specialization": "Cardiology"},
            "drjohn": {"password": "123", "name": "Johnson", "specialization": "Neurology"}
        },
        "nurses": {
            "nurse1": {"password": "123", "name": "Nurse Brown", "department": "Emergency"},
            "nurse2": {"password": "123", "name": "Nurse Davis", "department": "ICU"}
        }
    }
 
def save_user_data(data):
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
 
# Medical data storage
MEDICAL_DATA_FILE = "medical_data.json"
 
def load_medical_data():
    if os.path.exists(MEDICAL_DATA_FILE):
        with open(MEDICAL_DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        "P001": {"prescriptions": [], "doctor_notes": [], "vital_signs": []},
        "P002": {"prescriptions": [], "doctor_notes": [], "vital_signs": []},
        "P003": {"prescriptions": [], "doctor_notes": [], "vital_signs": []},
        "P004": {"prescriptions": [], "doctor_notes": [], "vital_signs": []},
        "P005": {"prescriptions": [], "doctor_notes": [], "vital_signs": []}
    }
 
def save_medical_data(data):
    with open(MEDICAL_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
 
current_user = None

# Head tracking function (runs continuously)
def head_tracking_loop():
    global head_tracking_active, blink_detection_active
    
    print("👀 Head tracking STARTED")
    print("🖱️ Move your head to control mouse cursor")
    print("👁️ Blink to click")
    
    # Eye blink detection variables
    click_pause = False
    click_time = 0
    
    cam = cv2.VideoCapture(0)
    screen_w, screen_h = pyautogui.size()
    pyautogui.FAILSAFE = False
    
    try:
        while head_tracking_active:
            ret, frame = cam.read()
            if not ret:
                print("🚫 Camera feed lost.")
                break
            
            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            output = face_mesh.process(rgb_frame)
            landmark_points = output.multi_face_landmarks
            frame_h, frame_w, _ = frame.shape

            if landmark_points:
                landmarks = landmark_points[0].landmark

                # Head tracking (move cursor) - using eye corners for better precision
                for id, landmark in enumerate(landmarks[474:478]):
                    x = int(landmark.x * frame_w)
                    y = int(landmark.y * frame_h)
                    cv2.circle(frame, (x, y), 3, (0, 255, 0))
                    if id == 1:
                        screen_x = screen_w * landmark.x
                        screen_y = screen_h * landmark.y
                        pyautogui.moveTo(screen_x, screen_y)

                # Blink detection (click)
                left = [landmarks[145], landmarks[159]]
                for lm in left:
                    x = int(lm.x * frame_w)
                    y = int(lm.y * frame_h)
                    cv2.circle(frame, (x, y), 3, (0, 255, 255))

                if not click_pause and (left[0].y - left[1].y) < 0.004:
                    pyautogui.click()
                    click_pause = True
                    click_time = time.time()
                    print("👁️ Blink detected - Click!")

                if click_pause and time.time() - click_time > 1.2:
                    click_pause = False
                
    except Exception as e:
        print(f"❌ Head tracking error: {e}")
    finally:
        cam.release()
        cv2.destroyAllWindows()
        print("🔴 Head tracking stopped")
 
class VoiceController:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.translator = Translator()
        self.microphone = None
        self.stop_listening = None
       
        try:
            self.microphone = sr.Microphone()
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
            print("✅ Microphone ready")
        except Exception as e:
            print(f"❌ Microphone not available: {e}")
            self.microphone = None
       
        # All supported languages for voice input
        self.language_codes = {
            'en': 'en-US',
            'es': 'es-ES',
            'ar': 'ar-AR',
            'fr': 'fr-FR',
            'de': 'de-DE',
            'it': 'it-IT',
            'pt': 'pt-PT',
            'ru': 'ru-RU',
            'zh': 'zh-CN',
            'ja': 'ja-JP'
        }
       
        print("✅ Voice Controller initialized")
 
    def voice_callback(self, recognizer, audio):
        """Background voice recognition callback"""
        try:
            # Get current language
            current_lang = current_user.get('language', 'en') if current_user else 'en'
            speech_code = self.language_codes.get(current_lang, 'en-US')
            lang_name = LANGUAGES.get(current_lang, 'English')
            
            # Convert speech to text in the selected language
            speech_text = recognizer.recognize_google(audio, language=speech_code)
            print(f"🎧 Heard in {lang_name}: '{speech_text}'")
            
            # Always translate non-English to English for command execution
            if current_lang != 'en':
                try:
                    translated = self.translator.translate(speech_text, src=current_lang, dest='en')
                    english_command = translated.text
                    print(f"🔄 Translated to English: '{english_command}'")
                    self.execute_command(english_command.lower())
                except Exception as e:
                    print(f"❌ Translation failed: {e}")
                    # Fallback: try to execute the original command
                    self.execute_command(speech_text.lower())
            else:
                # If already English, execute directly
                self.execute_command(speech_text.lower())
            
        except sr.UnknownValueError:
            print(f"❌ Could not understand {lang_name} audio")
        except sr.RequestError as e:
            print(f"❌ Speech recognition error: {e}")
        except Exception as e:
            print(f"❌ Voice callback error: {e}")

    def execute_command(self, command):
        """Execute voice commands with intelligent pattern matching"""
        print(f"🎯 Executing: {command}")
        
        # Normalize command
        command = command.lower().strip()
        words = command.split()
        
        # Scroll commands
        if ('scroll' in command and 'down' in command) or command in ['down', 'scroll down']:
            pyautogui.scroll(-200)
            print("✅ Scroll down executed")
        
        elif ('scroll' in command and 'up' in command) or command in ['up', 'scroll up']:
            pyautogui.scroll(200)
            print("✅ Scroll up executed")
        
        # Click commands with context
        elif any(word in command for word in ['double click', 'double press', 'two clicks']):
            pyautogui.doubleClick()
            print("✅ Double click executed")
        
        elif any(word in command for word in ['right click', 'right press', 'context menu']):
            pyautogui.rightClick()
            print("✅ Right click executed")
        
        elif any(word in command for word in ['click', 'press', 'select', 'tap']):
            pyautogui.click()
            print("✅ Click executed")
        
        # Application commands
        elif any(phrase in command for phrase in ['open chrome', 'launch chrome', 'start chrome', 'open browser']):
            pyautogui.hotkey('win', 'r')
            time.sleep(0.3)
            pyautogui.write('chrome')
            pyautogui.press('enter')
            print("✅ Chrome opened")
        
        elif any(phrase in command for phrase in ['open notepad', 'launch notepad', 'start notepad', 'open text editor']):
            pyautogui.hotkey('win', 'r')
            time.sleep(0.3)
            pyautogui.write('notepad')
            pyautogui.press('enter')
            print("✅ Notepad opened")
        
        # Text input commands (most flexible)
        elif any(keyword in command for keyword in ['type', 'write', 'enter', 'input']):
            # Handle different phrasing patterns
            if 'type' in command:
                text = command.split('type', 1)[1].strip()
            elif 'write' in command:
                text = command.split('write', 1)[1].strip()
            elif 'enter' in command:
                text = command.split('enter', 1)[1].strip()
            elif 'input' in command:
                text = command.split('input', 1)[1].strip()
            else:
                text = command
            
            # Clean the text
            text = self.clean_text_for_typing(text)
            if text:
                pyautogui.write(text)
                print(f"✅ Typed: '{text}'")
            else:
                print("❌ No text found to type")
        
        # System control
        elif any(word in command for word in ['stop', 'exit', 'quit', 'close system']):
            global voice_control_active, head_tracking_active
            voice_control_active = False
            head_tracking_active = False
            if self.stop_listening:
                self.stop_listening(wait_for_stop=False)
            print("🛑 All systems stopped via voice command")
        
        else:
            print(f"❓ Unknown command: {command}")

    def clean_text_for_typing(self, text):
        """Remove common command words from text to type"""
        if not text:
            return ""
        
        filter_words = [
            'the', 'a', 'an', 'some', 'my', 'your', 'this', 'that',
            'text', 'words', 'sentence', 'phrase', 'message', 'content'
        ]
        
        words = text.split()
        cleaned_words = [word for word in words if word.lower() not in filter_words]
        
        return ' '.join(cleaned_words)

    def start_voice_control(self):
        """Start background voice listening"""
        global voice_control_active
        if self.microphone:
            voice_control_active = True
            self.stop_listening = self.recognizer.listen_in_background(
                self.microphone, 
                self.voice_callback
            )
            print("🎙️ Voice control activated in background")
            return True
        else:
            print("❌ Cannot start voice control - no microphone")
            return False

    def stop_voice_control(self):
        """Stop background voice listening"""
        global voice_control_active
        voice_control_active = False
        if self.stop_listening:
            self.stop_listening(wait_for_stop=False)
            print("🔴 Voice control stopped")

# Start both systems simultaneously
def start_hands_free_system():
    global head_tracking_active, voice_control_active
    
    print("🚀 Starting Hands-Free System...")
    print("🔊 Voice control: ACTIVE")
    print("👀 Head tracking: ACTIVE")
    print("👁️ Blink to click: ENABLED")
    
    # Start voice control
    vc = VoiceController()
    voice_success = vc.start_voice_control()
    
    # Start head tracking
    head_tracking_active = True
    head_thread = threading.Thread(target=head_tracking_loop)
    head_thread.daemon = True
    head_thread.start()
    
    # Keep both systems running
    try:
        while voice_control_active and head_tracking_active:
            time.sleep(1)
    except KeyboardInterrupt:
        print("🛑 System stopped by user")
    finally:
        head_tracking_active = False
        vc.stop_voice_control()
        print("🔴 All systems stopped")

# Control routes
@app.route('/start_hands_free')
def start_hands_free_route():
    global head_tracking_active, voice_control_active
    
    if not head_tracking_active and not voice_control_active:
        system_thread = threading.Thread(target=start_hands_free_system)
        system_thread.daemon = True
        system_thread.start()
        return jsonify({'success': True, 'message': 'Hands-free system started!'})
    return jsonify({'success': False, 'message': 'System already active'})

@app.route('/stop_hands_free')
def stop_hands_free_route():
    global head_tracking_active, voice_control_active
    head_tracking_active = False
    voice_control_active = False
    return jsonify({'success': True, 'message': 'Hands-free system stopped!'})
 
@app.route('/')
def welcome_page():
    return render_template('welcome.html')
 
@app.route('/login')
def login_page():
    return render_template('login.html')
 
@app.route('/signup')
def signup_page():
    return render_template('signup.html')
 
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    name = data.get('name')
    user_type = data.get('user_type')
   
    if not all([username, password, name, user_type]):
        return jsonify({'success': False, 'message': 'All fields are required'})
   
    user_data = load_user_data()
   
    # Check if username already exists
    for user_category in user_data.values():
        if username in user_category:
            return jsonify({'success': False, 'message': 'Username already exists'})
   
    # Generate patient ID for patients
    patient_id = None
    if user_type == 'patients':
        patient_count = len(user_data['patients']) + 1
        patient_id = f"P{patient_count:03d}"
   
    # Add new user
    new_user = {
        'password': password,
        'name': name,
        'language': 'en'
    }
   
    if patient_id:
        new_user['patient_id'] = patient_id
    if user_type == 'doctors':
        new_user['specialization'] = data.get('specialization', 'General')
    elif user_type == 'nurses':
        new_user['department'] = data.get('department', 'General')
   
    user_data[user_type][username] = new_user
    save_user_data(user_data)
   
    return jsonify({'success': True, 'message': 'Account created successfully!'})
 
@app.route('/api/login', methods=['POST'])
def login():
    global current_user
    username = request.form['username']
    password = request.form['password']
    selected_language = request.form.get('language', 'en')
   
    user_data = load_user_data()
   
    for user_type, users in user_data.items():
        if username in users and users[username]['password'] == password:
            # Update user's language preference in database
            users[username]['language'] = selected_language
            save_user_data(user_data)
           
            current_user = {
                'username': username,
                'name': users[username]['name'],
                'type': user_type,
                'patient_id': users[username].get('patient_id', ''),
                'specialization': users[username].get('specialization', ''),
                'department': users[username].get('department', ''),
                'language': selected_language
            }
           
            session['current_language'] = selected_language
           
            if user_type == 'patients':
                # Start both systems simultaneously when patient logs in
                system_thread = threading.Thread(target=start_hands_free_system)
                system_thread.daemon = True
                system_thread.start()
                
                lang_name = LANGUAGES.get(selected_language, 'English')
                return jsonify({
                    'success': True,
                    'user_type': 'patient',
                    'message': f'Hands-free system activated! Voice: {lang_name}, Head tracking: Active'
                })
            elif user_type == 'doctors':
                return jsonify({
                    'success': True,
                    'user_type': 'doctor',
                    'message': f'Welcome Dr. {users[username]["name"]}'
                })
            else:
                return jsonify({
                    'success': True,
                    'user_type': 'nurse',
                    'message': f'Welcome {users[username]["name"]}'
                })
   
    return jsonify({'success': False, 'message': 'Invalid username or password'})
 
@app.route('/change_language/<lang_code>')
def change_language(lang_code):
    if lang_code in ['en', 'es', 'ar', 'fr', 'de', 'it', 'pt', 'ru', 'zh', 'ja']:
        session['current_language'] = lang_code
        if current_user:
            current_user['language'] = lang_code
        lang_name = LANGUAGES.get(lang_code, 'Unknown')
        return jsonify({'success': True, 'message': f'Language changed to {lang_name}'})
    return jsonify({'success': False, 'message': 'Invalid language code'})
 
@app.route('/current_language')
def current_language():
    current_lang = session.get('current_language', 'en')
    lang_name = LANGUAGES.get(current_lang, 'English')
    return jsonify({'language': current_lang, 'name': lang_name})
 
@app.route('/dashboard')
def dashboard():
    if not current_user:
        return redirect('/')
   
    if current_user['type'] == 'patients':
        return render_template('patient_dashboard.html', user=current_user)
    elif current_user['type'] == 'doctors':
        return render_template('doctor_dashboard.html', user=current_user)
    else:
        return render_template('nurse_dashboard.html', user=current_user)

# Medical endpoints (your existing medical functions)
@app.route('/api/save_prescription', methods=['POST'])
def save_prescription():
    if current_user and current_user['type'] == 'doctors':
        data = request.json
        medical_data = load_medical_data()
        
        patient_id = data['patient_id']
        medication = data['medication']
        dosage = data['dosage']
        
        if patient_id in medical_data:
            medical_data[patient_id]['prescriptions'].append({
                'medication': medication,
                'dosage': dosage,
                'prescribed_by': current_user['name'],
                'date': datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            save_medical_data(medical_data)
            return jsonify({'success': True, 'message': 'Prescription saved!'})
    
    return jsonify({'success': False, 'message': 'Doctors only can prescribe'})

@app.route('/api/save_diagnosis', methods=['POST'])
def save_diagnosis():
    if current_user and current_user['type'] == 'doctors':
        data = request.json
        medical_data = load_medical_data()
        
        patient_id = data['patient_id']
        diagnosis = data['diagnosis']
        treatment = data['treatment']
        
        if patient_id in medical_data:
            medical_data[patient_id]['doctor_notes'].append({
                'type': 'diagnosis',
                'diagnosis': diagnosis,
                'treatment': treatment,
                'doctor': current_user['name'],
                'date': datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            save_medical_data(medical_data)
            return jsonify({'success': True, 'message': 'Diagnosis saved!'})
    
    return jsonify({'success': False, 'message': 'Doctors only can diagnose'})

@app.route('/api/save_vitals', methods=['POST'])
def save_vitals():
    if current_user and current_user['type'] == 'nurses':
        data = request.json
        medical_data = load_medical_data()
        
        patient_id = data['patient_id']
        blood_pressure = data['blood_pressure']
        heart_rate = data['heart_rate']
        temperature = data['temperature']
        notes = data.get('notes', '')
        
        if patient_id in medical_data:
            medical_data[patient_id]['vital_signs'].append({
                'blood_pressure': blood_pressure,
                'heart_rate': heart_rate,
                'temperature': temperature,
                'notes': notes,
                'nurse': current_user['name'],
                'date': datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            save_medical_data(medical_data)
            return jsonify({'success': True, 'message': 'Vital signs recorded!'})
    
    return jsonify({'success': False, 'message': 'Nurses only can record vitals'})

@app.route('/api/save_nurse_note', methods=['POST'])
def save_nurse_note():
    if current_user and current_user['type'] == 'nurses':
        data = request.json
        medical_data = load_medical_data()
        
        patient_id = data['patient_id']
        note = data['note']
        
        if patient_id in medical_data:
            medical_data[patient_id]['doctor_notes'].append({
                'type': 'nurse_observation',
                'note': note,
                'nurse': current_user['name'],
                'date': datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            save_medical_data(medical_data)
            return jsonify({'success': True, 'message': 'Observation saved!'})
    
    return jsonify({'success': False, 'message': 'Nurses only'})

@app.route('/api/patient_data')
def get_patient_data():
    if current_user and current_user['type'] in ['doctors', 'nurses']:
        medical_data = load_medical_data()
        return jsonify({'success': True, 'data': medical_data})
    
    return jsonify({'success': False, 'message': 'Unauthorized'})

@app.route('/debug_users')
def debug_users():
    user_data = load_user_data()
    return jsonify(user_data)
 
@app.route('/reset_users')
def reset_users():
    user_data = {
        "patients": {
            "john": {"password": "123", "name": "John Smith", "patient_id": "P001", "language": "en"},
            "sarah": {"password": "123", "name": "Sarah Johnson", "patient_id": "P002", "language": "es"},
            "ali": {"password": "123", "name": "Ali Hassan", "patient_id": "P003", "language": "ar"},
            "marie": {"password": "123", "name": "Marie Dubois", "patient_id": "P004", "language": "fr"},
            "multilang": {"password": "123", "name": "Multi Language User", "patient_id": "P005", "language": "en"}
        },
        "doctors": {
            "drsmith": {"password": "123", "name": "Dr. Smith", "specialization": "Cardiology"},
            "drjohn": {"password": "123", "name": "Dr. Johnson", "specialization": "Neurology"}
        },
        "nurses": {
            "nurse1": {"password": "123", "name": "Nurse Brown", "department": "Emergency"},
            "nurse2": {"password": "123", "name": "Nurse Davis", "department": "ICU"}
        }
    }
    save_user_data(user_data)
    return "Users reset successfully!"
 
@app.route('/logout')
def logout():
    global current_user, voice_control_active, head_tracking_active
    voice_control_active = False
    head_tracking_active = False
    current_user = None
    session.clear()
    return redirect('/')
 
if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')
   
    print("🏥 Hospital System Starting...")
    print("🚀 HANDS-FREE SYSTEM READY!")
    print("🔊 Voice Control + 👀 Head Tracking = ACTIVE TOGETHER")
    print("👤 Test account: john / 123")
    print("🗣️ 10 Languages Supported: English, Spanish, Arabic, French, German, Italian, Portuguese, Russian, Chinese, Japanese")
    print("🔄 All non-English commands are automatically translated to English")
    print("👁️ Move head to control cursor, Blink to click")
    print("🌐 Welcome at: http://localhost:5000")
    app.run(debug=True, port=5000)