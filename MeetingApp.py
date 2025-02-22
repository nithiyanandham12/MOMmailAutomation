import streamlit as st
import os
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from faster_whisper import WhisperModel
import tempfile
import time
from dotenv import load_dotenv
from groq import Groq
from pydub import AudioSegment

# Load environment variables
load_dotenv()
groq_api_key = os.getenv("GROQ_API_KEY")
email_sender = os.getenv("EMAIL_SENDER")
email_password = os.getenv("EMAIL_PASSWORD")

client = Groq(api_key=groq_api_key)

# Streamlit UI
st.set_page_config(page_title="AI Meeting Summarizer", layout="wide")
st.title("📢 AI-Powered Meeting Summarizer & MoM Generator")
st.markdown("Upload your meeting audio/video and get a structured summary & MoM document sent to your email! 📩")

# Sidebar for Upload & Email Input
st.sidebar.header("📂 Upload & Email")
uploaded_file = st.sidebar.file_uploader("Upload a Meeting Audio/Video (MP3, WAV, MP4, AVI)", type=["mp3", "wav", "mp4", "avi"])
email_recipient = st.sidebar.text_input("📧 Enter recipient email(s) (comma-separated)")
email_cc = st.sidebar.text_input("📧 Enter CC email(s) (comma-separated, optional)")

# Store transcript, summary, and MoM in session state
if "transcript_text" not in st.session_state:
    st.session_state.transcript_text = ""
if "meeting_summary" not in st.session_state:
    st.session_state.meeting_summary = ""
if "mom_template_clean" not in st.session_state:
    st.session_state.mom_template_clean = ""

# Function to convert any audio format to WAV
def convert_to_wav(file_path):
    temp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
    audio = AudioSegment.from_file(file_path)
    audio = audio.set_channels(1).set_frame_rate(16000)  # Convert to mono, 16kHz
    audio.export(temp_wav, format="wav")
    return temp_wav

# Function to Transcribe Using `faster-whisper`
def transcribe_audio_whisper(file_path):
    # Convert to WAV if necessary
    if not file_path.endswith(".wav"):
        file_path = convert_to_wav(file_path)

    # Load the Whisper model (choose a lightweight model for better performance)
    model = WhisperModel("small", compute_type="int8")

    # Transcribe
    segments, _ = model.transcribe(file_path)
    transcript_text = " ".join([seg.text for seg in segments])

    return transcript_text

# Process uploaded file
if uploaded_file and not st.session_state.transcript_text:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
        temp_audio.write(uploaded_file.read())
        temp_audio_path = temp_audio.name

    st.sidebar.markdown("### 🔍 Transcribing Meeting... Please wait!")
    progress_bar = st.sidebar.progress(0)

    def update_progress():
        for i in range(1, 101, 10):
            time.sleep(0.5)
            progress_bar.progress(i)

    update_progress()
    st.session_state.transcript_text = transcribe_audio_whisper(temp_audio_path)
    progress_bar.empty()

    # Generating Summary
    summary_prompt = f"Extract the most important discussion points concisely from this meeting transcript: {st.session_state.transcript_text}"
    messages_summary = [{"role": "user", "content": summary_prompt}]
    completion_summary = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages_summary,
        temperature=0.6,
        max_completion_tokens=300,
        top_p=0.95,
        stream=False,
    )
    st.session_state.meeting_summary = completion_summary.choices[0].message.content

    # Generating MoM
    mom_prompt = f"Create a structured minutes of meeting document with clear action items and key decisions from this transcript: {st.session_state.transcript_text}"
    messages_mom = [{"role": "user", "content": mom_prompt}]
    completion_mom = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages_mom,
        temperature=0.6,
        max_completion_tokens=500,
        top_p=0.95,
        stream=False,
    )
    st.session_state.mom_template_clean = completion_mom.choices[0].message.content

# Main UI
col1, col2 = st.columns(2)
with col1:
    st.markdown("### 📜 Transcription")
    st.text_area("Meeting Transcription", st.session_state.transcript_text, height=250)

with col2:
    st.markdown("### 📌 Meeting Summary")
    st.text_area("Summary of Meeting", st.session_state.meeting_summary, height=250)

st.markdown("### 📑 Minutes of Meeting")
st.text_area("📜 Minutes of Meeting", st.session_state.mom_template_clean, height=300)

# Send email function
def send_email(to_email, cc_email, subject, body):
    msg = MIMEMultipart()
    msg["From"] = email_sender
    msg["To"] = to_email
    msg["Cc"] = cc_email if cc_email else ""
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    recipients = to_email.split(",") + (cc_email.split(",") if cc_email else [])

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(email_sender, email_password)
        server.sendmail(email_sender, recipients, msg.as_string())

if st.sidebar.button("📩 Send Minutes of Meeting via Email"):
    send_email(email_recipient, email_cc, "Minutes of Meeting", st.session_state.mom_template_clean)
    st.sidebar.success(f"📧 MoM sent successfully to {email_recipient} and CC: {email_cc}")
