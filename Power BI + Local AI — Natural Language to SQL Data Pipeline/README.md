# 📊 Power BI + Local AI — Natural Language to SQL Data Pipeline

A fully local AI-powered data pipeline that connects **Power BI Desktop**, **Ollama**, **Qwen 2.5 7B**, and **Microsoft SQL Server** to transform natural-language questions into SQL queries and automatically return the results to Power BI for visualization.

Instead of relying on an autonomous AI agent to continuously orchestrate database tools, this project uses **Power Query M** as the orchestration layer. Power BI sends a structured prompt containing database schema metadata to a locally hosted LLM, receives a generated T-SQL query, executes that query against SQL Server, and loads the resulting dataset into Power BI.

The architecture keeps the AI and database components on the local machine, making it suitable for experimenting with **privacy-conscious AI analytics workflows** without sending database content to an external LLM API.

---

## 🚀 What This Project Does

The pipeline allows a user to enter a request such as:

```text
historical trends for Malaria
```

The system then:

```text
Natural Language Request
        │
        ▼
Power BI Parameter
        │
        ▼
Power Query M
        │
        │  Schema + User Request
        ▼
Local Ollama Server
        │
        ▼
Qwen 2.5 7B
        │
        │  Generated T-SQL
        ▼
Power Query
        │
        ▼
Microsoft SQL Server
        │
        │  Query Results
        ▼
Power BI Dataset
        │
        ▼
📊 Interactive Visualizations
```

The result is a workflow where a user can describe the data they want in natural language while the underlying SQL generation and database processing remain local.

---

# 🏗️ System Architecture

```text
┌──────────────────────────────────────┐
│           Power BI Desktop           │
│                                      │
│  UserAIQuery Parameter               │
│        │                             │
│        ▼                             │
│  Power Query M                       │
│        │                             │
└────────┼─────────────────────────────┘
         │
         │ HTTP POST
         ▼
┌──────────────────────────────────────┐
│          Local Ollama Server         │
│          localhost:11434             │
│                                      │
│        Qwen 2.5 7B                  │
│        qwen-8k                       │
│        Context: 8192 tokens         │
└────────┼─────────────────────────────┘
         │
         │ Generated T-SQL
         ▼
┌──────────────────────────────────────┐
│        Microsoft SQL Server          │
│                                      │
│        DataAnalysis Database         │
│        health_indicators Table       │
│                                      │
│        Read-Only AI_Analyst User     │
└────────┼─────────────────────────────┘
         │
         │ Query Results
         ▼
┌──────────────────────────────────────┐
│             Power BI                 │
│                                      │
│     Tables • Charts • Dashboards     │
└──────────────────────────────────────┘
```

---

# 🔄 How the Pipeline Works

### 1. User Input

The user enters a natural-language request through a Power BI parameter:

```text
historical trends for Malaria
```

Other examples include:

```text
trends for HIV/AIDS
```

```text
metrics tracking Immunization
```

---

### 2. Prompt Construction

Power Query combines the user's request with the known database schema.

For example:

```text
Table: health_indicators

Columns:
GHO_DISPLAY
STARTYEAR
COUNTRY_DISPLAY
Numeric
```

The schema information provides the LLM with the structural context required to generate a SQL query.

---

### 3. Local AI SQL Generation

Power Query sends the prompt to the locally hosted Ollama API:

```text
Power BI
   │
   └── HTTP POST
          │
          ▼
   localhost:11434
          │
          ▼
      Qwen 2.5 7B
          │
          ▼
      T-SQL Query
```

No external LLM API is required for the SQL-generation step.

---

### 4. SQL Execution

The generated SQL is passed back to Power Query and executed against the local SQL Server database.

The database connection uses a restricted SQL Server account assigned to:

```text
db_datareader
```

This provides an additional database-level permission boundary.

> **Important:** A read-only database account is an important safeguard, but it should not be treated as a complete defense against every form of prompt injection or malformed SQL. Production implementations should also validate generated SQL before execution.

---

### 5. Power BI Visualization

The resulting rows are returned to Power BI and become the source for the dashboard visuals.

For example:

```text
User:
"historical trends for Malaria"

        ↓

AI-generated SQL

        ↓

SQL Server

        ↓

YEAR | COUNTRY | AVG_VALUE
-----|---------|----------
2020 | Eswatini|  ...
2021 | Eswatini|  ...
2022 | Eswatini|  ...
2023 | Eswatini|  ...

        ↓

Power BI Line Chart
```

---

# 📅 Dataset & Data Source

The demonstration environment uses public health data from the **Humanitarian Data Exchange (HDX)** and the **World Health Organization (WHO) Global Health Observatory**.

- **Source:** [Humanitarian Data Exchange](https://humdata.org)
- **Dataset Provider:** World Health Organization Global Health Observatory
- **Country Profile:** Eswatini
- **Example Dataset:** `health_indicators_swz.csv`

The dataset contains historical health indicators that can be queried through natural-language requests.

---

# 🗄️ Database Schema

The demonstration dataset is loaded into a SQL Server table called:

```text
health_indicators
```

### Columns

| Column | Type | Description |
|---|---|---|
| `GHO_DISPLAY` | `nvarchar` | Health indicator description |
| `STARTYEAR` | `int` | Year associated with the observation |
| `COUNTRY_DISPLAY` | `nvarchar` | Country or geographical entity |
| `Numeric` | `float` | Numerical indicator value |

Example indicators include:

```text
Malaria incidence
Antiretroviral therapy coverage
Tuberculosis notifications
Immunization indicators
```

---

# 🔒 Privacy & Security Architecture

One of the main goals of this project is to demonstrate how AI-assisted analytics can be implemented while keeping the AI and database components local.

### Local LLM

The LLM runs locally through Ollama:

```text
localhost:11434
```

The project does not require an external LLM API for SQL generation.

### Schema-Based Prompting

The LLM receives database structure and query requirements rather than being given unrestricted access to the database.

### Read-Only Database Account

The SQL Server connection uses a dedicated account assigned to:

```text
db_datareader
```

This prevents the account from performing normal data modification operations such as:

```sql
INSERT
UPDATE
DELETE
DROP
```

### Local Processing

The intended architecture keeps the following components on the same host:

```text
Power BI
   ↓
Power Query
   ↓
Ollama
   ↓
Qwen 2.5
   ↓
SQL Server
```

This makes the project particularly useful for exploring **local AI, private analytics, and AI-assisted SQL generation**.

---

# 🧠 Why Use Power Query as the Orchestration Layer?

A key design decision in this project was to avoid relying on a fully autonomous AI agent for database interaction.

Traditional agent architecture might look like:

```text
LLM
 ↓
Tool Call
 ↓
Database
 ↓
Tool Result
 ↓
LLM
 ↓
Tool Call
 ↓
...
```

This can introduce additional complexity around:

- Tool-calling reliability
- Agent loops
- Context limits
- Timeout handling
- Quantized model behavior
- Connection management

This project takes a different approach:

```text
User Request
      ↓
Power Query
      ↓
LLM → SQL
      ↓
SQL Server
      ↓
Power BI
```

The LLM is therefore focused primarily on **SQL generation**, while Power Query handles the deterministic orchestration.

This separation makes the architecture simpler and easier to debug.

---

# 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| **Power BI Desktop** | Data visualization and user interface |
| **Power Query M** | Data transformation and orchestration |
| **Ollama** | Local LLM serving |
| **Qwen 2.5 7B** | Local SQL-generation model |
| **Microsoft SQL Server** | Relational database |
| **SSMS** | Database administration |
| **Python** | Supporting data/AI experimentation |
| **Git/GitHub** | Version control and project documentation |

---

# ⚙️ Installation & Setup

## 1. Install Ollama

Install Ollama and download the Qwen 2.5 model.

Example:

```cmd
ollama pull qwen2.5:7b-instruct-q4_K_M
```

Verify the model:

```cmd
ollama list
```

---

## 2. Create the 8K Context Model

Create:

```text
qwen-8k.modelfile
```

with:

```text
FROM qwen2.5:7b-instruct-q4_K_M

PARAMETER num_ctx 8192
```

Then create the model:

```cmd
ollama create qwen-8k -f qwen-8k.modelfile
```

Verify:

```cmd
ollama list
```

You should see:

```text
qwen-8k
```

---

# 🗄️ 3. Configure the SQL Server Read-Only User

Open SQL Server Management Studio and create a dedicated login.

```sql
CREATE LOGIN AI_Analyst
WITH PASSWORD = 'YourSecureAIPassword123!';
GO

USE DataAnalysis;
GO

CREATE USER AI_Analyst FOR LOGIN AI_Analyst;
GO

ALTER ROLE db_datareader ADD MEMBER AI_Analyst;
GO
```

For a real deployment, use a strong password and follow your organization's credential-management practices.

---

# 🔌 4. Create the Power Query AI Function

Open:

```text
Power BI Desktop
    ↓
Transform Data
    ↓
Power Query Editor
    ↓
New Source
    ↓
Blank Query
```

Rename the query:

```text
AskQwen
```

Open **Advanced Editor** and use:

```powerquery
(promptText as text) =>
let
    HostUrl = "http://localhost:11434/api/generate",

    RequestBody = Json.FromValue([
        model = "qwen-8k:latest",
        prompt =
            "You are a senior data engineer writing Microsoft T-SQL for SQL Server. " &
            "Read the request and output ONLY the raw SQL query. " &
            "Do not use markdown code fences. " &
            "Do not use backticks. " &
            "Use single quotes for SQL strings. " &
            "Prompt: " & promptText,
        stream = false
    ]),

    Response =
        Web.Contents(
            HostUrl,
            [
                Headers = [
                    #"Content-Type" = "application/json"
                ],
                Content = RequestBody
            ]
        ),

    JsonResponse = Json.Document(Response),

    CleanSQL = JsonResponse[response]

in
    CleanSQL
```

---

# 🎛️ 5. Create the Power BI User Parameter

In Power Query:

```text
Manage Parameters
    ↓
New Parameter
```

Create:

```text
Name: UserAIQuery
Type: Text
```

Example value:

```text
historical trends for Malaria
```

---

# 🔗 6. Connect the Generated SQL to SQL Server

Create another blank query and use:

```powerquery
let
    MyPrompt =
        "Write a Microsoft T-SQL SELECT statement from the health_indicators table tracking "
        & UserAIQuery
        & ". The columns available in this table are exactly: "
        & "GHO_DISPLAY, STARTYEAR, COUNTRY_DISPLAY, and Numeric. "
        & "Filter GHO_DISPLAY by converting it to lowercase using "
        & "LOWER(GHO_DISPLAY) LIKE and match the lowercase version of the keyword requested. "
        & "Select these three columns: STARTYEAR AS YEAR, COUNTRY_DISPLAY, "
        & "and the average of the Numeric column. "
        & "Group strictly by STARTYEAR and COUNTRY_DISPLAY.",

    GeneratedSQL = AskQwen(MyPrompt),

    Source =
        Sql.Database(
            "127.0.0.1",
            "DataAnalysis",
            [Query = GeneratedSQL]
        )

in
    Source
```

> **Security note:** For a production implementation, add SQL validation before passing generated text to `Sql.Database`. Restricting the database user to `db_datareader` provides an important permission boundary, but query validation is still recommended.

---

# ▶️ Using the Dashboard

Once the Power Query configuration is complete:

1. Open **Power BI Desktop**.
2. Select **Transform Data**.
3. Choose **Edit Parameters**.
4. Enter a natural-language request.
5. Click **OK**.
6. Select **Refresh**.

Example queries:

```text
historical trends for Malaria
```

```text
trends for HIV/AIDS
```

```text
metrics tracking Immunization
```

```text
show malaria trends by country
```

Power Query sends the request to the local Qwen model, retrieves the generated SQL, executes it against SQL Server, and returns the results to Power BI.

---

# 📈 Example Use Cases

This architecture can be adapted beyond the demonstration health dataset.

Potential applications include:

- Natural-language business intelligence
- Local AI analytics
- SQL query generation
- Private enterprise dashboards
- Healthcare analytics
- Operational reporting
- Data exploration
- Self-service BI
- AI-assisted data engineering
- Local LLM experimentation

The underlying pattern can also be adapted to other SQL Server databases by changing the schema metadata and prompt logic.

---

# 🧪 Project Goals

This project explores several practical questions:

### Can a small local LLM generate useful SQL?

Rather than requiring a large cloud-hosted model, the project experiments with a quantized 7B model running locally.

### Can Power Query act as an AI orchestration layer?

The project demonstrates how Power Query can combine:

- User input
- Schema metadata
- HTTP requests
- LLM responses
- SQL execution

within a Power BI workflow.

### Can AI-assisted analytics remain local?

The architecture demonstrates a possible approach for keeping the LLM and database components on the local machine instead of sending database information to a cloud AI service.

---

# ⚠️ Limitations & Considerations

This is an experimental project rather than a production-ready AI database agent.

Important considerations include:

- Generated SQL should be validated before execution.
- LLM-generated SQL is not guaranteed to be correct.
- Model performance depends on available CPU/GPU/RAM.
- Large schemas may exceed the model's effective context window.
- Power BI refresh behavior can affect the workflow.
- Localhost availability is required.
- The read-only SQL account limits database permissions but does not eliminate all risks.
- Production deployments should implement stronger query validation, logging, authentication, and monitoring.

---

# 🔮 Future Improvements

Potential improvements include:

- 🛡️ SQL query validation before execution
- 🔍 Automatic schema discovery
- 🧠 Better prompt engineering
- 📚 Retrieval-Augmented Generation (RAG) for large schemas
- ⚡ GPU acceleration
- 📝 Query logging and monitoring
- 🔐 Stronger authentication between services
- 🧪 Automated SQL validation/testing
- 📊 Dynamic chart selection
- 🤖 Multi-model comparison
- ☁️ Optional hybrid local/cloud architecture
- 🐳 Containerized deployment with Docker

---

# 📂 Project Structure

A possible repository structure:

```text
PowerBI-Local-AI/
│
├── README.md
│
├── power-query/
│   ├── AskQwen.pq
│   └── HealthIndicators.pq
│
├── ollama/
│   └── qwen-8k.modelfile
│
├── sql/
│   └── setup_readonly_user.sql
│
├── data/
│   └── README.md
│
└── screenshots/
    ├── architecture.png
    ├── power-bi-dashboard.png
    └── ollama-model.png
```

---

# 🧩 Key Concept

The core idea behind this project can be summarized as:

```text
Natural Language
       ↓
   Power BI
       ↓
 Power Query
       ↓
 Local LLM
       ↓
     SQL
       ↓
 SQL Server
       ↓
    Results
       ↓
   Power BI
```

Rather than building an autonomous agent that controls the database, the project treats the LLM as a **local SQL-generation component** and lets Power BI and SQL Server handle the deterministic parts of the workflow.

---

# 👨‍💻 Author

**Nduduzo Dlamini**

**Data Analyst & Engineer | SQL Server, ETL & AI Tooling**

Interested in **Data Science, AI, SQL, networking, systems administration, and AI-powered analytics**.

🌐 [nduduzodlamini.com](https://nduduzodlamini.com)

---

## ⭐ If You Find This Project Interesting

Feel free to explore the implementation, experiment with different local models, and adapt the architecture to your own datasets.

This project is intended as a practical exploration of the intersection between:

**Local AI + SQL + Power BI + Data Engineering + Privacy-Conscious Analytics**

---
