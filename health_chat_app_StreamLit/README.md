# Eswatini Health Dashboard 🇸🇿

**Ask a health question. Get a chart.**

HEAD
The Eswatini Health Dashboard is a Streamlit app that helps people explore health indicators using plain English instead of SQL, spreadsheets, or data portals.

**Try the online demo:** [ai-health-dashboard.streamlit.app](https://ai-health-dashboard.streamlit.app)

> **Privacy note:** The online demo uses public WHO data and may use a hosted AI model. Do not enter confidential or personal information into it. For sensitive data, run the app locally with SQL Server and Ollama.

## See it in action

Ask questions such as:
=======
**Live app:** [i-health-dashboard.streamlit.app](https://i-health-dashboard.streamlit.app)

Example questions:
 36dfd66 (about page)

- `NCD trends line graph`
- `malaria deaths 2010 to 2024 pie chart`
- `Show me HIV prevalence 2005-2022 as a bar chart`

The app identifies a relevant health indicator, builds a read-only query, retrieves the data, and creates a visualisation.

## Online demo vs offline version

The **online version is a demo** so that anyone can try the app. The full setup runs **offline** on the author's computer.

| | Online demo | Offline version |
|---|---|---|
| Database | A bundled copy of the data (`health_indicators.db`, SQLite) | SQL Server on the author's computer |
| AI that reads questions | Built-in templates, or a hosted AI service if one is connected (limited requests) | **Qwen** running locally through Ollama |
| Internet | Needed | **Not needed**: works fully offline |
| Where your data goes | Hosted online, so do not type sensitive information | **Nothing leaves the computer**: no data leakage |
| Cost | Free hosting | **No AI subscription** to pay |
| Saved charts, FAQ and questions | On the hosting server, may be lost on restart | On the computer |

**Why Qwen?** It is what the author's computer can handle. The model is just a setting, so with better hardware a larger, more capable model can be used with the same app.

---

## Features

### Ask questions in plain English
- Turn natural-language questions into line, bar, area, pie, or scatter charts—or a table.
- Specify a chart type and year range in your question.
- Use the built-in FAQ for common questions.
- If an AI model is unavailable, built-in templates can still generate SQL.

### Understand the trend
- Each chart includes a headline metric: totals for yearly counts, or the latest value for rates and percentages.
- A change badge compares the first and latest years.
- Badge colours reflect the configured direction of improvement: green for healthier movement, red for movement in the wrong direction, and grey where there is no clear good direction.
- Adjust the year range, chart type, labels, grid lines, charts per row, and appearance.

### Export and report
- Download each chart's underlying data as an Excel file.
- Generate an AI-assisted report in Word (`.docx`) or Markdown.
- Ask a report question to focus the report on a topic represented on the dashboard.
- Report figures and changes are calculated in code rather than invented by the AI. Word reports also include a data table for each chart.

<<<<<<< HEAD
### Improve answers over time
- Questions the app cannot answer can be saved to an admin inbox.
- An administrator can turn an unanswered question into an FAQ entry.
- FAQ entries can provide an indicator, chart type, year range, written answer, or a combination of these.
- The app stores the question text, not the visitor's identity. Visitors are warned not to enter personal details.
=======
**About page**
- The **ℹ️ About** button opens a page that summarises the app, explains who can do what, and states the limitations (limited data and limited hardware for running bigger AI models). A visitor can be sent straight to it with `?page=about` added to the app's address.

**Shared dashboard**
- Charts are saved on the server and shown to every visitor, and they survive a page reload.
- Visitors can add charts. Only the admin can delete them.
>>>>>>> 36dfd66 (about page)

### Shared dashboard
- Charts are saved and shown to all visitors.
- Visitors can add charts; only the administrator can remove them.
- On Streamlit Community Cloud, local files may reset when the app restarts or is redeployed. See [Keeping dashboard data online](#keeping-dashboard-data-online).

## Privacy-first local deployment

The app is designed to support a fully local setup for work involving sensitive data:

- **Database:** SQL Server on your own computer or local network.
- **AI:** A local Qwen model served by Ollama.
- **Processing:** Questions, queries, charts, exports, and reports can be handled on your machine.
- **SQL safeguards:** Only a single read-only `SELECT` query is accepted for execution.

For the local privacy-focused setup, choose **SQL Server** and **Ollama** under **Advanced: data and LLM**, and leave `LLM_API_KEY` unset. In `.streamlit/config.toml`, set `gatherUsageStats = false` under `[browser]` if you want to disable Streamlit usage statistics.

**Important:** “Fully offline” depends on your configuration and environment. Use local SQL Server and Ollama, do not configure an online AI endpoint, and disable usage statistics. The public demo is not the private deployment: it uses a bundled SQLite database containing public WHO data and can use a hosted AI model. Never put confidential or personal data into the online demo.

## Data source

The dashboard's health indicators for Eswatini come from the World Health Organization (WHO) data published on the Humanitarian Data Exchange (HDX):

[WHO data for Eswatini on HDX](https://data.humdata.org/dataset/who-data-for-swz/resource/4e085174-bbff-4e15-8e23-b1aacaf92cad)

The data is loaded into the `health_indicators` table, with one row per indicator, year, and breakdown. Charts, headline values, and report calculations are based on this table. Check the dataset's licence and terms on HDX before reusing the data.

## How it works

```text
Question
   |
   v
catalog.py  -> identify indicator, years, chart type
   |
   v
sqlgen.py   -> build a database-specific SQL template
   |           optional AI rewrite, validated before use
   v
app.py      -> execute query and display chart
   |
   v
helpers.py  -> headline metrics, change badges, exports and reports
```

- `catalog.py` maps keywords to WHO indicator codes.
- `sqlgen.py` creates SQL for SQLite or SQL Server.
- AI-generated SQL is rejected if it is not a single read-only `SELECT`, does not match the planned indicator and columns, or targets the wrong database type. The built-in template is used instead.
- The sidebar's year range can filter the returned data without running another query.

## User and admin roles

| Capability | Visitor | Admin |
|---|---:|---:|
| Ask questions and add charts | Yes | Yes |
| Download Excel and generate reports | Yes | Yes |
| Use the FAQ list | Yes | Yes |
| Change chart settings for their own view | Yes | Yes |
| Rename charts created in their session | Yes | Yes |
| Rename any chart | No | Yes |
| View or edit SQL | No | Yes |
| Delete charts, clear the dashboard, or download the SQL log | No | Yes |
| Change database, AI, and breakdown settings | No | Yes |
| Manage FAQs and unanswered questions | No | Yes |

These permissions are enforced in the app logic, not just by hiding interface controls. Visitors receive generic error messages rather than raw SQL or technical details.

## Teach the dashboard with FAQs

The FAQ feature does not retrain the AI model. Instead, FAQ entries guide the app when similar questions are asked.

1. Log in as admin and open **FAQ: train the answers**.
2. Add a question and alternative phrasings.
3. Choose an indicator, chart type, and year range, and/or provide a written answer.
4. Use **Test a question** to check which FAQ matches.

The app can use matching FAQ entries to provide a chart, a written answer, or both. FAQ examples can also help the AI identify indicators and provide background context for reports.

## Unanswered-question inbox

When the app cannot answer a visitor's question, it can save the question text, the reason it failed, how often it was asked, and when it was asked. It does not save the visitor's identity.

The inbox keeps the 200 most recent questions. Similar questions may be grouped together. An administrator can turn a question into an FAQ, dismiss it, clear the list, or download `unanswered.json`.

Questions entered while logged in as admin are not saved, so administrators can test freely. Technical failures, such as a database outage, are written to server logs rather than being treated as unanswered health questions.

**Privacy reminder:** Do not enter personal details into questions. If you need a formal privacy notice for your deployment, add one that reflects your organisation's actual policies and legal obligations.

## Project structure

| File | Purpose |
|---|---|
| `run.bat` | Windows launcher |
| `README.md` | Project documentation |
| `app/app.py` | Streamlit interface, roles, saved charts, FAQs, and reports |
| `app/catalog.py` | Indicator catalog and question parsing |
| `app/helpers.py` | Headline metrics, change colours, Excel/Word exports, report text, FAQ matching |
| `app/sqlgen.py` | SQL generation, AI integration, and database-specific SQL handling |
| `app/requirements.txt` | Python dependencies |
| `tools/export_data.py` | Exports SQL Server data to the bundled SQLite database |
| `data/health_indicators.db` | Bundled SQLite copy used online |
| `assets/logo.png`, `assets/author.jpg` | App images |
| `.streamlit/config.toml` | Streamlit configuration |
| `.streamlit/secrets.toml` | Local secrets; do not commit |

Runtime files include:

- `data/dashboard.json` — shared dashboard charts.
- `data/faq.json` — FAQ entries.
- `data/unanswered.json` — unanswered-question inbox.
- `data/sql_log.sql` and `data/ui_prefs.json` — local SQL log and appearance preferences.

## Keeping dashboard data online

On Streamlit Community Cloud, files written while the app runs may reset after a restart or redeployment.

To preserve dashboard and FAQ state, download `dashboard.json` and `faq.json` from the admin interface and follow your repository's data-management process before redeploying. Be careful: committed files may be visible to anyone with access to a public repository. In particular, the dashboard file may contain SQL. The unanswered-question file may contain visitor-submitted text and is intentionally excluded from Git.

<<<<<<< HEAD
For persistent multi-user storage, consider moving runtime state to a database with appropriate access controls.
=======
- **SQL Server** (the local default): server `127.0.0.1`, database `DataAnalysis`, table `health_indicators`, ODBC Driver 17 with Windows authentication. All of these can be changed in the Advanced section.
- **Bundled SQLite file** (`health_indicators.db`): no server needed. This is what the online app always uses, because it cannot reach SQL Server on your PC.

After the SQL Server table changes, run `python export_data.py` to refresh `health_indicators.db`.

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

The offline version uses **Ollama** on your PC with a Qwen model (default `http://localhost:11434/api/generate`, model `qwen-8k:latest`), chosen in Advanced. Qwen is used because it is what the author's computer can handle; with better hardware, enter a larger model name in the same box.

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

On Streamlit Community Cloud, files written while the app runs (`dashboard.json`, `faq.json`) are **reset when the app reboots or is redeployed**. To keep them:

1. As admin, download the files (**Advanced → Download dashboard.json**, **FAQ → Download faq.json**).
2. Commit them to GitHub next to `app.py`. If `dashboard.json` is listed in `.gitignore`, remove that line.

`unanswered.json` is reset in the same way, and it holds visitors' questions. It is listed in `.gitignore` on purpose, so it is never committed to GitHub (important if the repository is public). Download it from the inbox when you want to keep a copy.

If your repository is public, committed files (including the SQL stored in `dashboard.json`) are visible to anyone. For fully permanent storage, move them to a database.

---
>>>>>>> 36dfd66 (about page)

## Security notes

- Only a single read-only `SELECT` is accepted for execution; statements and keywords associated with writes or administrative operations are rejected.
- AI-generated SQL is checked against the intended indicator, columns, and database type before it can be used.
- Admin login uses constant-time password comparison and locks after five incorrect attempts per session.
- Visitors do not see raw SQL or technical error messages.
- Excel exports treat visitor text as plain text to reduce spreadsheet-formula risks.
- Keep `.streamlit/secrets.toml` out of source control.
- For local privacy-focused use, ensure the database and AI settings point to local services and that no online AI API key or endpoint is configured.

Security controls reduce risk but are not a substitute for deployment-specific security review, access controls, backups, and privacy governance.

## Troubleshooting

| Problem | What to check |
|---|---|
| Repository files are out of date | Update `app.py`, `catalog.py`, `helpers.py`, and `sqlgen.py` together, then restart the app |
| Admin login is disabled | Set `ADMIN_PASSWORD` and restart |
| Online SQL syntax error near `AS` | Update the app files; saved charts from older versions may contain SQL Server SQL |
| Charts disappear after an online reboot | Review the [Keeping dashboard data online](#keeping-dashboard-data-online) section |
| FAQ inbox stays empty | Questions entered while logged in as admin are not saved; test while logged out |
| AI report ignores a question | Add a chart about that topic to the dashboard; reports use matching charts |

## 👨‍💻 Author

**Nduduzo Dlamini**

Data Analyst & Engineer | SQL Server, ETL & AI Tooling</p>

- **Portfolio:** [nduduzodlamini.com](https://nduduzodlamini.com)
- **GitHub:** [NduduzoDlamini](https://github.com/NduduzoDlamini)


---

If you find the project useful, try the [online demo](https://ai-health-dashboard.streamlit.app) and share feedback or suggest a health question it should support.
