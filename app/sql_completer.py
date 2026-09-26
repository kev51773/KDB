import re
from typing import Dict, List, Any
import sqlglot
from sqlglot import exp

def get_sql_completions(
    sql_query: str,
    cursor_pos: int,
    schema_data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Generates smart SQL completions using sqlglot AST parsing and schema data.
    """
    # 1. Truncate query up to cursor position
    text_before = sql_query[:cursor_pos] if cursor_pos <= len(sql_query) else sql_query
    
    # Extract current word being typed
    word_match = re.search(r'([a-zA-Z0-9_\.]+)$', text_before)
    full_word = word_match.group(1) if word_match else ""
    
    alias_prefix = ""
    prefix = full_word.lower()
    
    if "." in full_word:
        parts = full_word.split(".")
        alias_prefix = parts[0].lower()
        prefix = parts[1].lower() if len(parts) > 1 else ""

    # 2. Extract schema tables map { table_name: [column_names] }
    schema_map = {} # lowercase_table -> list of column dicts
    real_case_map = {}
    
    tables_list = schema_data.get("tables", []) + schema_data.get("views", [])
    for t in tables_list:
        t_name = t["name"]
        schema_map[t_name.lower()] = [c["name"] for c in t.get("columns", [])]
        real_case_map[t_name.lower()] = t_name

    # 3. Use sqlglot to parse AST and extract tables & aliases in scope
    tables_in_scope = {} # alias_or_table -> real_table_name
    try:
        parsed = sqlglot.parse_one(text_before)
        if parsed:
            for table in parsed.find_all(exp.Table):
                t_name = table.name.lower()
                alias = table.alias.lower() if table.alias else t_name
                tables_in_scope[alias] = t_name
                tables_in_scope[t_name] = t_name
    except Exception:
        # Fallback regex for incomplete/partial SQL AST
        matches = re.findall(r'(?:from|join|update|into)\s+([a-zA-Z0-9_]+)(?:\s+(?:as\s+)?([a-zA-Z0-9_]+))?', text_before, re.IGNORECASE)
        for t_name, alias in matches:
            if t_name:
                tn_lower = t_name.lower()
                tables_in_scope[tn_lower] = tn_lower
                if alias and alias.lower() not in ('where', 'on', 'join', 'left', 'right', 'inner', 'outer', 'group', 'order', 'limit', 'set', 'values'):
                    tables_in_scope[alias.lower()] = tn_lower

    suggestions = []
    added = set()

    # 4. Handle Alias Dot completion e.g. "p.n" or "users.e"
    if alias_prefix:
        target_table = tables_in_scope.get(alias_prefix, alias_prefix)
        if target_table in schema_map:
            for col in schema_map[target_table]:
                if col.lower().startsWith(prefix) if hasattr(col.lower(), 'startsWith') else col.lower().startswith(prefix):
                    if col.lower() not in added:
                        added.add(col.lower())
                        suggestions.push({
                            "text": col,
                            "displayText": f"{col}  ⚡ [{alias_prefix}]",
                            "type": "column"
                        }) if hasattr(suggestions, 'push') else suggestions.append({
                            "text": col,
                            "displayText": f"{col}  ⚡ [{alias_prefix}]",
                            "type": "column"
                        })
        return suggestions

    # 5. Check if user is typing right after FROM / JOIN / INTO
    is_after_from = bool(re.search(r'(?:from|join|into|update)\s+[a-zA-Z0-9_]*$', text_before, re.IGNORECASE))

    if is_after_from:
        # Prioritize Tables
        for t_lower, real_t in real_case_map.items():
            if t_lower.startswith(prefix):
                suggestions.append({
                    "text": real_t,
                    "displayText": f"{real_t}  📁 [table]",
                    "type": "table"
                })
        return suggestions

    # 6. Default Context: Columns from tables in scope
    target_tables = list(set(tables_in_scope.values())) if tables_in_scope else list(schema_map.keys())

    for t_lower in target_tables:
        if t_lower in schema_map:
            real_t = real_case_map.get(t_lower, t_lower)
            for col in schema_map[t_lower]:
                col_key = col.lower()
                if col_key.startswith(prefix) and col_key not in added:
                    added.add(col_key)
                    suggestions.append({
                        "text": col,
                        "displayText": f"{col}  ⚡ [col:{real_t}]",
                        "type": "column"
                    })

    # 7. Tables (if prefix matches table name)
    for t_lower, real_t in real_case_map.items():
        if t_lower.startswith(prefix) and t_lower not in added:
            added.add(t_lower)
            suggestions.append({
                "text": real_t,
                "displayText": f"{real_t}  📁 [table]",
                "type": "table"
            })

    # 8. Keywords (lowest priority)
    sql_keywords = [
        "SELECT", "FROM", "WHERE", "AND", "OR", "LIMIT", "ORDER BY", "GROUP BY", "HAVING",
        "INSERT INTO", "UPDATE", "DELETE FROM", "JOIN", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN",
        "ON", "AS", "IN", "IS NULL", "IS NOT NULL", "LIKE", "BETWEEN", "COUNT", "SUM", "AVG", "MIN", "MAX",
        "DISTINCT", "UNION", "ALL", "NOT", "EXISTS", "CASE", "WHEN", "THEN", "ELSE", "END"
    ]

    if schema_data.get("is_read_only"):
        write_kws = {"INSERT INTO", "INSERT", "UPDATE", "DELETE FROM", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "REPLACE"}
        sql_keywords = [kw for kw in sql_keywords if kw not in write_kws]

    if prefix:
        for kw in sql_keywords:
            if kw.lower().startswith(prefix) and kw.lower() not in added:
                added.add(kw.lower())
                suggestions.append({
                    "text": kw,
                    "displayText": f"{kw}  🔑 [keyword]",
                    "type": "keyword"
                })

    return suggestions
