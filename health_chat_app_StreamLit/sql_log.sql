-- ======================================================================
-- Eswatini Health Dashboard - SQL log
-- Updated  : 2026-10-13 22:11
-- Database : DataAnalysis
-- Charts   : 2
-- ======================================================================

-- ----------------------------------------------------------------------
-- [1] Malaria trends from 2010 to 2024
-- Prompt    : show malaria trends from 2010 to 2024 in a line graph
-- Indicator : MALARIA_EST_INCIDENCE - Estimated malaria incidence (per 1000 population at risk)
-- Created   : unknown
-- SQL by    : LLM
-- ----------------------------------------------------------------------
SELECT
    TRY_CAST(STARTYEAR AS INT) AS [year],
    CAST(Numeric AS FLOAT) AS [value],
    [DIMENSION_CODE] AS [series]
FROM health_indicators
WHERE GHO_CODE = 'MALARIA_EST_INCIDENCE'
  AND Numeric IS NOT NULL
  AND TRY_CAST(STARTYEAR AS INT) IS NOT NULL
  AND TRY_CAST(STARTYEAR AS INT) BETWEEN 2010 AND 2024
ORDER BY [year] ASC, [series] ASC;

-- ----------------------------------------------------------------------
-- [2] HIV prevalence from 2010 to 2024
-- Prompt    : Show HIV prevalence from 2010 to 2024 in a bar graph
-- Indicator : MDG_0000000029 - Prevalence of HIV among adults aged 15 to 49 (%)
-- Created   : unknown
-- SQL by    : LLM
-- ----------------------------------------------------------------------
SELECT
    TRY_CAST(STARTYEAR AS INT) AS [year],
    CAST(Numeric AS FLOAT) AS [value],
    [DIMENSION_CODE] AS [series]
FROM health_indicators
WHERE GHO_CODE = 'MDG_0000000029'
  AND Numeric IS NOT NULL
  AND TRY_CAST(STARTYEAR AS INT) IS NOT NULL
ORDER BY [year] ASC, [series] ASC;

