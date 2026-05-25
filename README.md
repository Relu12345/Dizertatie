# Classroom Neurofeedback System

The repository is organized into the application code, the thesis source, and the final deliverable PDFs:

- [`application/`](./application): all application code
  - [`application/pi_runtime/`](./application/pi_runtime): Raspberry Pi Unicorn acquisition
  - [`application/teacher_app/`](./application/teacher_app): Windows teacher dashboard and stream monitor
- [`paper_code/`](./paper_code): LaTeX source of the master thesis
- [`pdfs/`](./pdfs): final PDFs of the thesis and the poster

Important:

- the working Unicorn Pi vendor library in this repo is `32-bit ARM`
- for the Raspberry Pi flow to work reliably, use a `32-bit Raspberry Pi OS` userspace

## Full Setup On A New Windows PC

### 1. Clone the repo

```powershell
git clone https://github.com/Relu12345/Dizertatie
cd Dizertatie
```

### 2. Create the Windows virtual environment

The teacher app currently uses the root project virtual environment on Windows.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r application\teacher_app\requirements.txt
```

### 3. Run the teacher app on Windows

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run application/teacher_app/run_dashboard.py
```

After that, open the Streamlit URL shown in the terminal.

## Pi Runtime

Deploy to the Pi:

```powershell
.\application\pi_runtime\deploy_to_pi.ps1 -PiHost <pi-hostname-or-ip> -PiUser <pi-user>
```

Run acquisition on the Pi:

```bash
cd ~/classroom-neurofeedback-pi
. .venv/bin/activate
python3 stream_unicorn_lsl.py --lsl-name Unicorn --single-channel --channel-name "EEG 1"
```

## Full Run Flow

1. On Windows, activate the root `.venv` and start the teacher app:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run application/teacher_app/run_dashboard.py
```

2. Deploy the Pi runtime from Windows:

```powershell
.\application\pi_runtime\deploy_to_pi.ps1 -PiHost <pi-hostname-or-ip> -PiUser <pi-user>
```

3. SSH into the Pi and start Unicorn acquisition:

```bash
cd ~/classroom-neurofeedback-pi
. .venv/bin/activate
python3 stream_unicorn_lsl.py --lsl-name Unicorn --single-channel --channel-name "EEG 1"
```

4. Back on Windows, open the Streamlit dashboard and watch for the `Unicorn` LSL stream.

## Thesis and Poster

- The LaTeX source of the thesis lives in [`paper_code/`](./paper_code) (`main.tex` is the entry point).
- The final compiled PDFs (thesis and poster) are kept in [`pdfs/`](./pdfs).
