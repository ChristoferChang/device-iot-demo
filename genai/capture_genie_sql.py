"""Captures Genie's generated-SQL behavior as committed evidence.

Asks real questions of the demo Genie space, polls each to completion, and
extracts the generated SQL + result rows. Run locally against fevm-azure:

    export DATABRICKS_HOST=https://adb-7405615395376229.9.azuredatabricks.net
    export DATABRICKS_TOKEN=$(databricks auth token --profile fevm-azure -o json | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
    python3 genai/capture_genie_sql.py          # writes evidence/genie_sql_transcript.md
"""
import os
import time

from databricks.sdk import WorkspaceClient

SPACE_ID = "01f1b456af5d124aacf95d5f5d8e3636"
OUT = os.path.join(os.path.dirname(__file__), "..", "evidence", "genie_sql_transcript.md")

QUESTIONS = [
    "Which machines have the highest health risk score and what is driving their risk?",
    "Show the fleet utilization trend by equipment class over the last 7 days.",
    "List machines with active fault codes and show their fault codes.",
]

w = WorkspaceClient()


def poll(space_id, conv_id, msg_id, timeout_s=240):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        msg = w.genie.get_message(space_id=space_id, conversation_id=conv_id, message_id=msg_id)
        raw = str(msg.status) if msg and msg.status else ""
        status = raw.split(".")[-1]
        if status in ("COMPLETED", "FAILED", "CANCELLED"):
            return msg, status
        time.sleep(5)
    raise TimeoutError("genie message did not complete in time")


def generated_sql_and_rows(space_id, conv_id, msg_id, msg):
    sql_text, rows, columns = "", [], []
    for att in msg.attachments or []:
        if att.query and att.query.query:
            sql_text = att.query.query
            att_id = att.attachment_id or att.query.id
            if att_id:
                try:
                    qr = w.genie.get_message_query_result_by_attachment(
                        space_id=space_id, conversation_id=conv_id,
                        message_id=msg_id, attachment_id=att_id)
                    sr = qr.statement_response
                    if sr:
                        columns = [c.name for c in sr.manifest.schema.columns]
                        data = sr.result.data_array if sr.result and sr.result.data_array else []
                        rows = [dict(zip(columns, r)) for r in data]
                except Exception as e:
                    print(f"  (query result fetch failed: {e})")
    return sql_text, columns, rows


transcript = [
    "# Genie generated-SQL transcript",
    "",
    "Live questions asked of the demo Genie space over the governed gold views.",
    "For each question: Genie's answer, the SQL it generated, and a sample of the rows returned.",
    f"Captured {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} on fevm-azure, space `{SPACE_ID}`,",
    "via the Genie Conversation API (`genai/capture_genie_sql.py`).",
    "",
]

for q in QUESTIONS:
    print(f"asking: {q}")
    started = w.genie.start_conversation(space_id=SPACE_ID, content=q)
    conv_id, msg_id = started.conversation_id, started.message_id
    msg, status = poll(SPACE_ID, conv_id, msg_id)
    transcript.append(f"## Q: {q}")
    transcript.append("")
    transcript.append(f"conversation_id `{conv_id}` · message_id `{msg_id}` · status **{status}**")
    if status != "COMPLETED":
        err = str(msg.error) if msg and msg.error else "unknown"
        transcript.append(f"")
        transcript.append(f"ERROR: message did not complete: {err}")
        continue

    sql_text, columns, rows = generated_sql_and_rows(SPACE_ID, conv_id, msg_id, msg)
    answer = ""
    for att in msg.attachments or []:
        if att.text and att.text.content:
            answer = att.text.content
            break

    transcript.append("")
    transcript.append("**Genie's answer:**")
    transcript.append("")
    for line in (answer or "(none)").splitlines()[:8]:
        transcript.append(f"> {line}")
    transcript.append("")
    transcript.append("**Generated SQL (executed against the governed views):**")
    transcript.append("")
    transcript.append("```sql")
    transcript.append(sql_text or "(no query generated)")
    transcript.append("```")
    transcript.append("")
    transcript.append(f"**Rows returned: {len(rows)}** — sample:")
    transcript.append("")
    if columns:
        transcript.append("| " + " | ".join(columns[:5]) + " |")
        transcript.append("|" + "---|" * min(len(columns), 5))
        for r in rows[:5]:
            vals = [str(r.get(c, ""))[:40] for c in columns[:5]]
            transcript.append("| " + " | ".join(vals) + " |")
    transcript.append("")
    print(f"  -> {status}, {len(rows)} rows")

with open(OUT, "w") as f:
    f.write("\n".join(transcript))
print(f"wrote {os.path.abspath(OUT)}")
