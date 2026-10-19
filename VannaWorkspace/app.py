import os
import json
from typing import Any, Dict, List

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from vanna import Agent, AgentConfig, MemoryConversationStore, User
from vanna.core.registry import ToolRegistry
from vanna.core.user.resolver import UserResolver
from vanna.core.system_prompt.default import DefaultSystemPromptBuilder

from vanna.integrations.ollama import OllamaLlmService
from vanna.integrations.chromadb import ChromaAgentMemory
from vanna.integrations.mssql import MSSQLRunner
from vanna.integrations.plotly import PlotlyChartGenerator

from vanna.tools import RunSqlTool, VisualizeDataTool
from vanna.servers.fastapi import VannaFastAPIServer


# ============================================================
# CONFIGURATION
# ============================================================

HOST = "127.0.0.1"
PORT = 8080

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "qwen-8k:latest"

SQL_SERVER = "127.0.0.1"
SQL_DATABASE = "DataAnalysis"
SQL_USER = "anythingllm_readonly"

ODBC_DRIVER = "ODBC Driver 17 for SQL Server"

CHROMA_PATH = r"G:\VannaWorkspace\vanna_local_storage"

SQL_ACCESS_GROUP = "sql_analyst"


# ============================================================
# SQL SERVER PASSWORD
# ============================================================

SQL_PASSWORD = os.getenv("VANNA_SQL_PASSWORD")

if not SQL_PASSWORD:
    raise RuntimeError(
        "VANNA_SQL_PASSWORD environment variable is not set.\n"
        "Set it before starting Vanna."
    )


# ============================================================
# SQL SERVER CONNECTION
# ============================================================

ODBC_CONN_STR = (
    f"DRIVER={{{ODBC_DRIVER}}};"
    f"SERVER={SQL_SERVER};"
    f"DATABASE={SQL_DATABASE};"
    f"UID={SQL_USER};"
    f"PWD={SQL_PASSWORD};"
    "TrustServerCertificate=yes;"
)

sql_runner = MSSQLRunner(
    odbc_conn_str=ODBC_CONN_STR
)


# ============================================================
# CUSTOM LINE CHART GENERATOR
# ============================================================

class ForcedLineChartGenerator(PlotlyChartGenerator):
    """
    Forces time-series results such as:

        year | value

    to use a Plotly line chart.

    Vanna's default PlotlyChartGenerator can interpret a numeric
    year column as a regular numeric variable and produce a
    scatter plot. This class detects year/time columns and forces
    them into a line chart.
    """

    def generate_chart(
        self,
        df: pd.DataFrame,
        title: str = "Chart"
    ):
        if df is None or df.empty:
            raise ValueError(
                "Cannot generate a chart from an empty dataset."
            )

        # --------------------------------------------------------
        # Identify likely time/year columns
        # --------------------------------------------------------

        year_columns = [
            col
            for col in df.columns
            if str(col).strip().lower()
            in {
                "year",
                "years",
                "startyear",
                "endyear",
                "year_display",
                "date",
                "datetime",
                "time",
                "period",
            }
        ]

        # --------------------------------------------------------
        # If a time column exists, force line chart
        # --------------------------------------------------------

        if year_columns:
            time_col = year_columns[0]

            numeric_cols = (
                df.select_dtypes(include=["number"])
                .columns
                .tolist()
            )

            value_cols = [
                col
                for col in numeric_cols
                if col != time_col
            ]

            if value_cols:
                return self._create_forced_line_chart(
                    df=df,
                    time_col=time_col,
                    value_cols=value_cols,
                    title=title,
                )

        # --------------------------------------------------------
        # Otherwise use Vanna's normal chart generation
        # --------------------------------------------------------

        return super().generate_chart(
            df,
            title
        )

    def _create_forced_line_chart(
        self,
        df: pd.DataFrame,
        time_col: str,
        value_cols: List[str],
        title: str,
    ):
        chart_df = df.copy()

        # --------------------------------------------------------
        # Detect year-like columns
        # --------------------------------------------------------

        time_col_lower = str(time_col).strip().lower()

        is_year_column = time_col_lower in {
            "year",
            "years",
            "startyear",
            "endyear",
            "year_display",
        }

        if is_year_column:
            chart_df[time_col] = pd.to_numeric(
                chart_df[time_col],
                errors="coerce"
            )

            chart_df = chart_df.dropna(
                subset=[time_col]
            )

            chart_df = chart_df.sort_values(
                by=time_col
            )

        # --------------------------------------------------------
        # Create Plotly figure
        # --------------------------------------------------------

        fig = go.Figure()

        colors = self.COLOR_PALETTE

        for i, col in enumerate(value_cols[:5]):
            fig.add_trace(
                go.Scatter(
                    x=chart_df[time_col],
                    y=chart_df[col],
                    mode="lines+markers",
                    name=str(col),
                    line=dict(
                        color=colors[i % len(colors)],
                        width=3,
                    ),
                    marker=dict(
                        size=7
                    ),
                    hovertemplate=(
                        f"{time_col}: %{{x}}"
                        f"<br>{col}: %{{y}}"
                        "<extra></extra>"
                    ),
                )
            )

        # --------------------------------------------------------
        # Layout
        # --------------------------------------------------------

        fig.update_layout(
            title=title,
            xaxis_title="Year",
            yaxis_title="Value",
            hovermode="x unified",
            autosize=True,
        )

        self._apply_standard_layout(fig)

        return json.loads(
            pio.to_json(fig)
        )


# ============================================================
# VISUALIZATION TOOL
# ============================================================

plotly_generator = ForcedLineChartGenerator()

visualize_tool = VisualizeDataTool(
    plotly_generator=plotly_generator
)


# ============================================================
# SQL TOOL
# ============================================================

sql_tool = RunSqlTool(
    sql_runner=sql_runner
)


# ============================================================
# TOOL REGISTRY
# ============================================================

tool_registry = ToolRegistry()

tool_registry.register_local_tool(
    sql_tool,
    access_groups=[SQL_ACCESS_GROUP]
)

tool_registry.register_local_tool(
    visualize_tool,
    access_groups=[SQL_ACCESS_GROUP]
)


# ============================================================
# LOCAL USER RESOLVER
# ============================================================

class SimpleUserResolver(UserResolver):

    async def resolve_user(
        self,
        request
    ) -> User:

        return User(
            id="local_user",
            email="local_user@localhost",
            group_memberships=[
                SQL_ACCESS_GROUP
            ],
        )


user_resolver = SimpleUserResolver()


# ============================================================
# CHROMA MEMORY
# ============================================================

agent_memory = ChromaAgentMemory(
    persist_directory=CHROMA_PATH
)


# ============================================================
# SYSTEM PROMPT
# ============================================================

SQL_SYSTEM_PROMPT = """
You are a local health-data SQL analyst.

DATABASE
- SQL Server database: DataAnalysis
- Main table: health_indicators

IMPORTANT COLUMNS
- GHO_CODE: machine-readable indicator code.
- GHO_DISPLAY: human-readable indicator name/description.
- STARTYEAR: beginning year of the observation.
- ENDYEAR: ending year of the observation when applicable.
- YEAR_DISPLAY: display year/period when applicable.
- Numeric: numerical value of the indicator.
- COUNTRY_DISPLAY: country name.
- DIMENSION: may contain additional breakdown information.
- DIMENSION_VALUE: value for an additional dimension when applicable.

============================================================
INDICATOR DISCOVERY
============================================================

Never assume that the user's wording is the exact GHO_CODE.

For example:

- "malaria" is a topic, not necessarily an indicator code.
- "diabetes" is a topic, not necessarily an indicator code.
- "NCD" is a topic/category, not necessarily one indicator.
- "malaria cases" should be matched against both GHO_CODE and
  GHO_DISPLAY.

When the user asks for an indicator or topic and the exact
GHO_CODE is unknown:

1. Search health_indicators using both GHO_CODE and GHO_DISPLAY.
2. Identify the most appropriate indicator from the returned
   results.
3. Use the actual GHO_CODE found in the database for the final
   data query.
4. Do not invent indicator codes.

Example indicator discovery query:

SELECT DISTINCT
    GHO_CODE,
    GHO_DISPLAY
FROM health_indicators
WHERE
    GHO_CODE LIKE '%malaria%'
    OR GHO_DISPLAY LIKE '%malaria%'
ORDER BY GHO_CODE;

Use the database's case-insensitive collation where available.

============================================================
CHOOSING AN INDICATOR
============================================================

When several indicators match a topic:

1. Prefer the indicator whose GHO_DISPLAY most closely matches
   the user's wording.
2. Prefer actual measurement indicators over metadata,
   descriptive, policy, or administrative indicators.
3. If the user explicitly asks for "cases", prefer an indicator
   describing cases.
4. If the user explicitly asks for "incidence", prefer an
   incidence indicator.
5. If the user explicitly asks for "mortality", prefer a
   mortality indicator.
6. If the user explicitly asks for "deaths", prefer a deaths
   indicator.
7. If several indicators remain equally appropriate and the
   difference materially changes the result, ask the user for
   clarification.
8. Never invent a GHO_CODE.

============================================================
TREND QUERIES
============================================================

When the user asks for a trend over time:

1. Identify the appropriate indicator.
2. Use STARTYEAR or YEAR_DISPLAY as the time dimension.
3. Use Numeric as the numerical value.
4. Return a simple result suitable for visualization.
5. Prefer two columns:

   year | value

Example:

SELECT
    CAST(STARTYEAR AS INT) AS [year],
    AVG(CAST(Numeric AS FLOAT)) AS [value]
FROM health_indicators
WHERE GHO_CODE = '<ACTUAL_CODE_FOUND_FROM_DATABASE>'
GROUP BY STARTYEAR
ORDER BY [year] ASC;

If the user specifies a country, include COUNTRY_DISPLAY
in the filter.

Example:

SELECT
    CAST(STARTYEAR AS INT) AS [year],
    AVG(CAST(Numeric AS FLOAT)) AS [value]
FROM health_indicators
WHERE
    GHO_CODE = '<ACTUAL_CODE_FOUND_FROM_DATABASE>'
    AND COUNTRY_DISPLAY = '<COUNTRY>'
GROUP BY STARTYEAR
ORDER BY [year] ASC;

============================================================
COUNTRY FILTERS
============================================================

When the user specifies a country:

- Use COUNTRY_DISPLAY when it contains the country name.
- Do not assume a country code unless the database schema
  provides one.
- If necessary, first inspect available COUNTRY_DISPLAY values.

Example:

SELECT DISTINCT COUNTRY_DISPLAY
FROM health_indicators
WHERE COUNTRY_DISPLAY LIKE '%Eswatini%'
ORDER BY COUNTRY_DISPLAY;

============================================================
VISUALIZATION
============================================================

If the user asks to:

- show a trend
- plot a trend
- graph a trend
- visualize data
- show changes over time
- display a chart
- create a chart
- plot the results

then:

1. Discover the correct indicator if necessary.
2. Execute the SQL query.
3. Pass the SQL result to the visualization tool.
4. Use a line chart for time-series data.
5. Do not tell the user to use Power BI.
6. Do not tell the user to use Tableau.
7. Do not tell the user to use Excel.
8. Do not tell the user to use Python.
9. Do not generate Python plotting code for the user.
10. The visualization must be produced by the visualization
    tool.

For a time-series result, prefer:

year | value

The visualization should use:

- X-axis = year
- Y-axis = value
- chart type = line
- markers may be displayed on the line.

============================================================
MULTIPLE INDICATORS
============================================================

If the user asks for multiple indicators:

1. Identify each indicator from GHO_CODE/GHO_DISPLAY.
2. Only use indicators that actually exist.
3. Do not invent missing indicators.

For comparison over time, prefer:

year | indicator | value

============================================================
AMBIGUOUS REQUESTS
============================================================

If several indicators match the user's wording:

- Prefer the closest GHO_DISPLAY match.
- Prefer actual measurements.
- Prefer the user's requested measure, such as cases,
  incidence, mortality, deaths, prevalence, or rate.
- If ambiguity materially changes the answer, ask for
  clarification.

============================================================
DATA VALIDATION
============================================================

Before presenting results:

- Make sure the SQL query actually returned data.
- Do not invent missing values.
- Do not fabricate years.
- Do not fabricate indicators.
- Do not fabricate countries.
- Do not fabricate numerical results.

If no matching indicator exists, explain that no matching
indicator was found instead of guessing.

============================================================
READ-ONLY SQL
============================================================

Only generate read-only SQL.

Allowed operations include:

- SELECT
- WITH / CTE
- GROUP BY
- ORDER BY
- WHERE
- JOIN
- HAVING
- aggregate functions
- CAST
- CONVERT
- CASE

Never execute:

- INSERT
- UPDATE
- DELETE
- DROP
- ALTER
- TRUNCATE
- CREATE
- MERGE

Never modify database objects.

Never expose database credentials.

============================================================
EXECUTION WORKFLOW
============================================================

Follow this workflow for analytical requests:

USER REQUEST
    ↓
Understand the requested topic/indicator
    ↓
Discover GHO_CODE if necessary
    ↓
Execute the required SQL
    ↓
If visualization requested:
    pass SQL result to visualization tool
    ↓
Return concise explanation

For a trend request, do not repeatedly regenerate the same
SQL query.

Once the required data has been successfully retrieved,
visualize that result rather than executing the same query
again unnecessarily.

============================================================
RESPONSE STYLE
============================================================

Be concise and analytical.

When returning a result, briefly state:

- which indicator was used
- what period was analyzed
- any important country/filter used

When a chart is requested, prioritize displaying the chart
rather than explaining how the user could create one elsewhere.
"""


# ============================================================
# SYSTEM PROMPT BUILDER
# ============================================================

system_prompt_builder = DefaultSystemPromptBuilder(
    base_prompt=SQL_SYSTEM_PROMPT
)


# ============================================================
# OLLAMA LLM
# ============================================================

llm_service = OllamaLlmService(
    model=OLLAMA_MODEL,
    host=OLLAMA_HOST
)


# ============================================================
# CONVERSATION STORE
# ============================================================

conversation_store = MemoryConversationStore()


# ============================================================
# Vanna AGENT
# ============================================================

agent = Agent(
    llm_service=llm_service,
    tool_registry=tool_registry,
    user_resolver=user_resolver,
    agent_memory=agent_memory,
    conversation_store=conversation_store,
    config=AgentConfig(
        max_tool_iterations=4,
        stream_responses=True,
        auto_save_conversations=True,
        include_thinking_indicators=False,
        temperature=0.0,
    ),
    system_prompt_builder=system_prompt_builder,
)


# ============================================================
# FASTAPI SERVER
# ============================================================

server = VannaFastAPIServer(agent)


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print("VANNA LOCAL HEALTH DATA ANALYST")
    print("=" * 70)

    print(f"Server:       http://{HOST}:{PORT}")
    print(f"Ollama:       {OLLAMA_HOST}")
    print(f"Model:        {OLLAMA_MODEL}")
    print(f"SQL Server:   {SQL_SERVER}")
    print(f"Database:     {SQL_DATABASE}")
    print(f"SQL User:     {SQL_USER}")
    print(f"Chroma:       {CHROMA_PATH}")
    print(f"Access Group: {SQL_ACCESS_GROUP}")

    print("=" * 70)
    print("Indicator discovery: GHO_CODE + GHO_DISPLAY")
    print("Visualization:       Forced Plotly line charts")
    print("SQL mode:            Read-only")
    print("=" * 70)

    server.run(
        host=HOST,
        port=PORT
    )