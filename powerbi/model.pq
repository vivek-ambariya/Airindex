// Power Query (M) — load and type the AIRINDEX export.
//
// Paste into Power BI Desktop: Home > Transform data > Advanced Editor.
// Change the file path on the first line to wherever the repo lives.
//
// Explicit types matter here. Power BI's type inference reads
// reading_date from a CSV as text on some locales, which silently breaks
// every time-intelligence measure downstream — and breaks it quietly,
// producing a chart that renders but sorts alphabetically.
let
    Source = Csv.Document(
        File.Contents("C:\path\to\aqi-india\powerbi\airindex_daily.csv"),
        [Delimiter = ",", Columns = 16, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"station",          type text},
        {"city",             type text},
        {"state",            type text},
        {"country_code",     type text},
        {"lat",              type number},
        {"lon",              type number},
        {"reading_date",     type date},
        {"year",             Int64.Type},
        {"month",            Int64.Type},
        {"parameter",        type text},
        {"value",            type number},
        {"n_hours",          Int64.Type},
        {"completeness",     type number},
        {"band",             type text},
        {"band_index",       Int64.Type},
        {"completeness_flag", type text}
    }, "en-GB"),

    // A month name for axis labels, and a sort key so it orders
    // Jan..Dec instead of Apr, Aug, Dec...
    WithMonthName = Table.AddColumn(Typed, "month_name",
        each Date.MonthName(#date(2000, [month], 1), "en-GB"), type text),

    // Season, matching the definition used in the Phase 6 analysis, so
    // the report and the write-up cannot disagree.
    WithSeason = Table.AddColumn(WithMonthName, "season", each
        if List.Contains({11, 12, 1}, [month]) then "Winter (Nov-Jan)"
        else if List.Contains({6, 7, 8, 9}, [month]) then "Monsoon (Jun-Sep)"
        else if List.Contains({3, 4, 5}, [month]) then "Summer (Mar-May)"
        else "Transition (Feb, Oct)", type text),

    // Usable = at or above the 50% completeness floor. Precomputed in
    // the export rather than recalculated here, so the report's notion
    // of "usable" is identical to the application's.
    WithUsable = Table.AddColumn(WithSeason, "is_usable",
        each [completeness_flag] = "usable", type logical)
in
    WithUsable
