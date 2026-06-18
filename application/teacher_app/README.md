# Teacher App

This folder contains the Windows-side teacher application.

It is responsible for:

- discovering live LSL streams
- showing stream status and live values
- visualizing raw Fz and attention history

## Files

- `run_dashboard.py`: Streamlit entrypoint
- `requirements.txt`: teacher app dependencies
- `src/classroom_neurofeedback/`: collector, attention processing, and UI

## Run

From the repo root:

```powershell
streamlit run teacher_app/run_dashboard.py
```
