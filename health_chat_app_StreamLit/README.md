# Eswatini Health Dashboard

**Live app: [ai-health-dashboard.streamlit.app](https://ai-health-dashboard.streamlit.app)**

A Streamlit app where you **ask for a health trend in plain English** and a chart appears. Each question adds a chart to a shared dashboard, with a headline number, a green/red change badge, Excel downloads and an AI-written report (Word or Markdown).

Example questions:

- `NCD trends line graph`
- `malaria deaths 2010 to 2024 pie chart`
- `Show me HIV prevalence 2005-2022 as a bar chart`

The data is Eswatini health indicators (World Health Organization Global Health Observatory indicator codes). See [Data source](#data-source).

---

## Features

**Asking questions**
- Type a question; the app finds the right indicator, builds a safe read-only SQL query, runs it and draws the chart.
- Name a chart type (line, bar, area, pie, scatter, table) and years in the question and they are used.
- Works with or without an AI model. If the AI is off or fails, a built-in template writes the SQL.
- A **❓ FAQ** list of common questions, one click each (see [FAQ](#faq-teaching-the-app-your-answers)).
- Questions the app cannot answer are saved for the admin, who can turn them into FAQ answers (see [Unanswered questions](#unanswered-questions)).

**Charts**
- Headline number per chart: the total for yearly counts, the latest value for rates and percentages.
- A change badge since the first year: **green** = moving in the healthier direction, **red** = the wrong way, **grey** = no clear good direction (see [Colours](#change-badge-colours)).
- Sidebar settings: start/end year, time frame, chart type, data labels, horizontal lines, charts per row, and Auto/Light/Dark appearance.
- A ⚙ menu on each chart for its own type, data labels and horizontal lines.

**Downloads and reports**
- **Excel per chart**: the chart's title on top, then exactly the rows and columns behind it. A second sheet, "All years", is added when the chart shows only part of the data.
- **AI report**: a general report, or type a question ("How was HIV in 2024 compared to 2022?") and the report answers it first. Download it as **Word (.docx)**, which also has a data table for every chart, or as Markdown. The numbers and changes are calculated in code, not by the AI. Without an AI, a built-in summary is written.

**Shared dashboard**
- Charts are saved on the server and shown to every visitor, and they survive a page reload.
- Visitors can add charts. Only the admin can delete them.

---

## Data source

The numbers come from the **World Health Organization (WHO) data for Eswatini**, published on the Humanitarian Data Exchange (HDX):

[WHO data for Eswatini on HDX](https://data.humdata.org/dataset/who-data-for-swz/resource/4e085174-bbff-4e15-8e23-b1aacaf92cad)

The dataset is loaded into the `health_indicators` table (one row per indicator, year and breakdown). Charts, headline numbers and AI reports are all calculated from it. Please check the licence and terms on the HDX page before reusing the data.

---

## Roles

| | User (no login) | Admin (password) |
|---|---|---|
| Ask questions, add charts | Yes | Yes |
| Excel per chart, AI report, FAQ list | Yes | Yes |
| Sidebar settings | Yes, except "Advanced" | All |
| Change a chart's type / data labels / lines | Own view only | Saved for everyone |
| Rename a chart | Only charts they created in this session | Any chart |
| See or edit the SQL | No | Yes |
| Remove a chart, Clear all, download the SQL log | No | Yes |
| "Advanced: data and LLM" (data source, AI, breakdown) | No | Yes |
| "FAQ: train the answers", including the unanswered-questions inbox | No | Yes |

These rules are enforced in the code, not just by hiding buttons. Visitors also never see SQL or technical error messages (they get a generic message; the details go to the server log and to the admin).

---

## How it works

```
question ──► catalog.py ──► indicator code, years, chart type
                │
                ▼
          sqlgen.py ──► SQL template (SQLite or SQL Server)
                │          optional AI rewrite, accepted only if
                │          read-only, right indicator, right columns
                ▼
          app.py ──► run query ──► chart + headline number (helpers.py)
```

- `catalog.py` maps words to indicator codes (for example "malaria" and "incidence" to `MALARIA_EST_INCIDENCE`).
- `sqlgen.py` builds the SQL. The SQL always fetches all years, so the sidebar year range filters instantly without re-querying.
- AI-written SQL is rejected if it is not a single read-only `SELECT`, does not follow the plan, or is written for the wrong database (SQL Server vs SQLite). The template is used instead.

---

## Project files

| File | Purpose |
|---|---|
| `run.bat` | Windows launcher script (stays in the main folder) |
| `README.md` | This file |
| `app/app.py` | The Streamlit app: pages, roles, saving, charts, FAQ, report |
| `app/catalog.py` | Indicator catalog and question parsing. **Add new indicators here** |
| `app/helpers.py` | KPI numbers, change colours, Excel and Word files, report text, FAQ matching |
| `app/sqlgen.py` | Safe SQL generation, the AI call, converting SQL between databases |
| `app/requirements.txt` | Python packages |
| `tools/export_data.py` | Copies the table from SQL Server into `data/health_indicators.db` |
| `data/health_indicators.db` | The bundled SQLite copy of the data (used online) |
| `assets/logo.png`, `assets/author.jpg` | Images shown in the app |
| `.gitignore` | Keeps secrets, local files and visitors' questions (`unanswered.json`) out of GitHub |
| `.streamlit/config.toml` | Streamlit settings (hides error details from visitors) |
| `.streamlit/secrets.toml` | Your passwords and keys. **Never commit it** |

Files the app creates while running (all in the `data/` folder):

| File | Contents |
|---|---|
| `data/dashboard.json` | The saved charts, shared by all visitors |
| `data/faq.json` | The FAQ entries |
| `data/unanswered.json` | Questions the app could not answer (the admin's inbox) |
| `data/sql_log.sql`, `data/ui_prefs.json` | Local only: the SQL of every chart, and the Appearance choice |

---

## Database and admin login

**Database.** Locally, the admin picks where the data is read from under **Advanced: data and LLM**:

- **SQL Server** (the local default): server `127.0.0.1`, database `DataAnalysis`, table `health_indicators`, ODBC Driver 17 with Windows authentication. All of these can be changed in the Advanced section.
- **Bundled SQLite file** (`data/health_indicators.db`): no server needed. This is what the online app always uses, because it cannot reach SQL Server on your PC.

After the SQL Server table changes, run `python tools/export_data.py` to refresh `data/health_indicators.db`.

**Admin login.** Set `ADMIN_PASSWORD` (see the next section), then use **🔒 Admin login** at the bottom of the sidebar. Until a password is set, admin login is switched off.

---

## Settings (secrets or environment variables)

| Name | What it does |
|---|---|
| `ADMIN_PASSWORD` | Turns on the admin login |
| `LLM_API_KEY` | Key for an online AI (any OpenAI-compatible API). Without it the online app uses built-in templates only |
| `LLM_BASE_URL` | AI address. Default `https://api.groq.com/openai/v1` |
| `LLM_MODEL` | AI model. Default `openai/gpt-oss-120b` |
| `HEALTH_APP_CLOUD` | `1` or `0` to force online or local behaviour |

Set them in `.streamlit/secrets.toml` (for example `ADMIN_PASSWORD = "a-long-password"`), in the hosting app's **Secrets** page, or as environment variables.

Locally you can instead use **Ollama** on your PC (default `http://localhost:11434/api/generate`, model `qwen-8k:latest`), chosen in Advanced.

Limits you can change at the top of `app.py`: `MAX_CHARTS` (60 charts on the dashboard), `ONLINE_AI_CALLS_PER_SESSION` (25 AI calls per visitor), `REPORT_MAX_CHARTS` (the report covers the 15 newest charts), and the chart sizes and axis title fonts.

---

## FAQ: teaching the app your answers

The AI model is not retrained. The FAQ guides the app instead:

1. Log in as admin and open **FAQ: train the answers**.
2. Add a **question**, other ways people ask it, the **indicator** to chart (and chart type and years), and optionally an **answer text**. You need an indicator, an answer, or both.
3. Use **Test a question** to see which FAQ a question would match.

What happens:
- A visitor's question that closely matches a FAQ gets your indicator, chart type, years and answer. Filler words, plurals and years are ignored when matching.
- A question with only a written answer ("What is HIV prevalence?") shows the answer. If the visitor clearly asked for a chart, they get the chart and the answer.
- A question containing an indicator code skips the FAQ.
- Your examples are given to the AI when it has to guess an indicator, and matching answers are given to the AI report as background notes.

---

## Unanswered questions

The app keeps a list of what visitors asked that it could not answer, so the admin can teach it.

**What gets saved** (the question text, why it failed, how many times it was asked, and when):

| Reason shown | When it happens |
|---|---|
| No indicator matched the question | Nothing in the catalog or FAQ fits, so the app only showed a search list |
| Indicator ... returned no data | An indicator was found (or typed) but has no rows |
| Report question: no chart on the dashboard about this topic | An AI report was asked about a topic with no chart |
| I couldn't find a health topic in that request | The question had no health topic in it at all |

The same question asked again, in a different word order or with different filler words or years, is counted once ("asked 3×") instead of being listed again. The list keeps the 200 most recent questions. Only the question text is stored, never who asked. Visitors are told this on the page: "If the dashboard cannot answer a question, the question (not your name) is saved so the admin can teach it the answer. Please do not type personal details." The AI report box says the same.

**What the admin does.** Open **FAQ: train the answers**. At the top is **📥 Unanswered questions**:

1. Press **🎓** to copy a question into the FAQ form below.
2. Choose the indicator to chart and/or write an answer, then press **Save FAQ**.
3. The question leaves the list automatically, along with any similar ones the new FAQ now answers.
4. Press **🗑** to dismiss a question that needs no answer, **Clear unanswered list** to empty it, or **Download unanswered.json** to keep a copy.

Good to know:
- Questions typed while you are logged in as admin are **not** saved, so you can test freely. To check that logging works, ask something unanswerable while logged out.
- Technical failures (for example the database is down) are **not** saved. They go to the server log only, so the list contains real unanswered questions.
- A question the FAQ answers (with a chart or a written answer) is not saved, unless its chart comes back empty.

---

## Change badge colours

Most indicators are a burden (cases, deaths, rates), so **lower is better**. The exceptions, where higher is better (coverage, life expectancy, workforce, water access and so on), are the `HIGHER_IS_BETTER` set at the top of the KPI section of `helpers.py`. `NO_CLEAR_DIRECTION` lists indicators that stay grey. Move a code between those sets to change its colour.

### Add an indicator

Add one line to `CATALOG` in `catalog.py`: `("keywords,comma,separated", "GHO_CODE", "Label (unit)")`. The first row of a topic is the default when the visitor names no measure. If an increase is good, also add the code to `HIGHER_IS_BETTER`; if the indicator is a yearly count that can be added up, add it to `COUNT_CODES` in `catalog.py`.

---

## Keeping your data safe online

On Streamlit Community Cloud, files written while the app runs (`data/dashboard.json`, `data/faq.json`) are **reset when the app reboots or is redeployed**. To keep them:

1. As admin, download the files (**Advanced → Download dashboard.json**, **FAQ → Download faq.json**).
2. Commit them to GitHub in the `data` folder. If `dashboard.json` is listed in `.gitignore`, remove that line.

`unanswered.json` is reset in the same way, and it holds visitors' questions. It is listed in `.gitignore` on purpose, so it is never committed to GitHub (important if the repository is public). Download it from the inbox when you want to keep a copy.

If your repository is public, committed files (including the SQL stored in `dashboard.json`) are visible to anyone. For fully permanent storage, move them to a database.

---

## Security notes

- The admin password is compared in constant time, and the admin login locks after 5 wrong tries per session.
- SQL is only run if it is a single read-only `SELECT`; keywords such as `INSERT`, `DROP` and `EXEC` are rejected.
- Visitors never see SQL or raw error messages. Set `showErrorDetails = "none"` (already in `config.toml`) to hide Python errors too.
- Keep `.streamlit/secrets.toml` out of GitHub.
- Excel files treat visitor text as plain text, so a title cannot run as a formula.
- Unanswered questions are stored as plain text without any visitor identity, and visitors are told so on the page. `unanswered.json` is in `.gitignore`. If you need a formal privacy notice, mention it there too.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "These files in your repository are out of date" | Upload the latest `app.py`, `catalog.py`, `helpers.py`, `sqlgen.py` together to the `app` folder, then reboot |
| "Admin login is off" | Set `ADMIN_PASSWORD` (see above) and restart |
| Online error "near AS: syntax error" | An old chart was saved with SQL Server SQL. Update to the latest files: charts are now rebuilt for SQLite automatically |
| Charts disappear after a reboot (online) | Commit `data/dashboard.json` to GitHub (see above) |
| Table looks dark in Light mode | Update `helpers.py` (tables are no longer flipped back to dark) |
| The unanswered list stays empty although you asked unanswerable questions | Questions typed while logged in as admin are not saved. Log out and ask again |
| The AI report ignores your question | Make sure a chart on that topic is on the dashboard; the report only uses charts that match the question |

---

## Author

Nduduzo Dlamini
