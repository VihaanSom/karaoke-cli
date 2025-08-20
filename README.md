# 🎤 Command-Line Karaoke Machine

Bring karaoke to your terminal — no fancy GUI, just pure coding fun.  
Built as a demo project for **ForTheLoveOfCode** 💻🎶

---

## 🚀 Features
- Play any `.mp3` file directly from the terminal.  
- Display synced `.lrc` lyric files line by line.  
- Pure Python — simple, hackable, and fun.  

---

## 🛠️ Requirements
Make sure you have Python 3 installed with:
```bash
pip install pygame
```

---

## ▶️ Demo Steps

### 1. Clone the repo (or copy files)
```bash
git clone https://github.com/VihaanSom/karaoke-cli.git
cd karaoke-cli
```

### 2. Run with a test file
We included a **demo audio + lyrics** so you can try right away:
```bash
python karaoke.py test_song.mp3 sample.lrc
```

Expected Output:
```
[00:01.00] 🎶 La la la...
[00:05.00] Singing in the terminal 🎤
[00:10.00] Code + Music = ❤️
```

### 3. Add your own songs
- Place your `.mp3` in the same folder.  
- Add/create an `.lrc` file (lyric timestamps).  
- Run the script:  
```bash
python karaoke.py your_song.mp3 your_song.lrc
```

---