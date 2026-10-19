# 🧠 Local AI Health Data Analyst

A locally hosted AI data analyst that allows users to explore public health data using natural-language questions. The project combines **Vanna 2.0, Ollama/Qwen, SQL Server, ChromaDB, FastAPI, and Plotly** to create a conversational analytics workflow that discovers health indicators, generates read-only SQL queries, retrieves results, and visualizes data through interactive charts.

## 🚀 Features

- **Natural-Language Queries:** Ask questions about health indicators in plain English.
- **AI-Powered SQL Generation:** Converts user questions into SQL queries.
- **Dynamic Indicator Discovery:** Searches health indicator codes and descriptions instead of relying on hardcoded indicator names.
- **Read-Only Data Access:** Designed for querying data without modifying the database.
- **Local LLM Integration:** Uses Ollama to run the Qwen model locally.
- **Interactive Visualizations:** Generates charts using Plotly.
- **Local Semantic Storage:** Uses ChromaDB to support retrieval of relevant information.
- **API Backend:** Uses FastAPI to provide the application interface.

## 🏗️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Application logic and data processing |
| Vanna 2.0 | Natural-language-to-SQL workflow |
| Ollama / Qwen | Local language model |
| Microsoft SQL Server | Health data storage and querying |
| ChromaDB | Vector storage and retrieval |
| FastAPI | API backend |
| Plotly | Interactive data visualization |
| pandas | Data handling and analysis |

## 📅 Dataset & Data Source

The project uses public health data from the **Humanitarian Data Exchange (HDX)**, provided by the **World Health Organization (WHO)**.

- **Source:** [HDX – WHO Data for Eswatini](https://data.humdata.org/dataset/who-data-for-swz/resource/4e085174-bbff-4e15-8e23-b1aacaf92cad)
- **Dataset Provider:** World Health Organization (WHO)
- **Country:** Eswatini
- **Database:** `DataAnalysis`
- **Table:** `health_indicators`

The dataset contains health indicators that can be explored through natural-language requests and analyzed using SQL queries and interactive visualizations.

## 🔄 How It Works

1. **Ask a question:** The user submits a natural-language question, such as *"Show me malaria trends in Eswatini."*
2. **Discover indicators:** The application searches indicator codes and descriptions to identify relevant health data.
3. **Generate SQL:** The local AI model generates an appropriate read-only SQL query.
4. **Retrieve results:** SQL Server executes the query and returns matching records.
5. **Visualize data:** Plotly generates an interactive chart when the returned data is suitable for visualization.

## 🛠️ Prerequisites

- Windows or another supported operating system
- Python 3.12
- Microsoft SQL Server
- Ollama
- A compatible Qwen model downloaded in Ollama
- The project database and health indicator data

## ⚙️ Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
```

Replace the repository URL with your actual GitHub repository URL.

### 2. Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

If the repository includes a `requirements.txt` file:

```powershell
pip install -r requirements.txt
```

Otherwise, install the dependencies specified by your project configuration.

### 4. Configure Ollama

Install Ollama and download the model used by the application. For example, if your local model is named `qwen-8k:latest`:

```powershell
ollama pull qwen-8k:latest
ollama run qwen-8k:latest
```

Ensure the Ollama service is running before starting the application.

### 5. Configure SQL Server

Create or restore the `DataAnalysis` database and ensure the `health_indicators` table contains the required health data.

Configure the database connection using environment variables. For example:

```powershell
$env:VANNA_SQL_PASSWORD="your_database_password"
```

Use the database connection settings expected by your application. Do not commit passwords, API keys, or other secrets to GitHub.

### 6. Run the application

Start the application using the entry point configured in your project. For example, if your FastAPI application is defined in `app.py`:

```powershell
python app.py
```

Use the actual startup command defined in your project if it differs.

## 💬 Example Questions

Try asking questions such as:

- "Show me malaria trends in Eswatini."
- "What health indicators are available for malaria?"
- "Show the trend in estimated malaria incidence over time."
- "Compare health indicators across available years."
- "Show me trends in noncommunicable disease indicators."

The results depend on the indicators, years, countries, and observations available in the database.

## 🔐 Security Considerations

- Use a dedicated database account with read-only permissions.
- Restrict generated SQL to approved read-only operations.
- Keep database credentials in environment variables rather than source code.
- Validate generated SQL before execution.
- Keep the application bound to localhost unless remote access is intentionally configured and secured.

**Note:** Local model execution does not by itself guarantee database security. SQL permissions and query validation should enforce read-only access.

## 🎯 Project Goal

This project explores how locally hosted language models can make health data more accessible by allowing users to ask questions in natural language, retrieve relevant information from a relational database, and understand results through interactive visualizations.

## 📌 Future Improvements

- Add more health datasets and indicators.
- Improve SQL validation and error handling.
- Add filters for country, year, and indicator.
- Expand chart types and export options.
- Improve conversational context across follow-up questions.
- Add automated tests and application logging.

## 👨‍💻 Author

**Nduduzo Dlamini**

Data Analyst & Engineer | SQL Server, ETL & AI Tooling</p>

- **Portfolio:** [nduduzodlamini.com](https://nduduzodlamini.com)
- **GitHub:** [NduduzoDlamini](https://github.com/NduduzoDlamini)
