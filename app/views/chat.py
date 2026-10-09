"""Ask DelayLens: chat with the flight data."""

import streamlit as st

from assistant import answer_question, get_api_key
from common import SITE_NAME, load, page_header

page_header(f"Ask {SITE_NAME}", "Ask about flights, delays, weather or news. Every answer shows the queries behind it.")

EXAMPLES = [
    "Which airline was the most punctual?",
    "Why were Mumbai flights so late on 8 October?",
    "Which flights to Delhi are late most often?",
    "What time of day is best to fly out of Bengaluru?",
    "What is in the news about flight disruption this week?",
]
QUESTION_LIMIT = 15  # per visit, to stay inside the free AI quota

if not get_api_key():
    st.warning("The AI assistant is not configured on this copy of the site (no API key).")
    st.stop()

days = load("airport_daily")["flight_date"]
st.caption(f"Data covers Mumbai, Bengaluru and Hyderabad departures from {days.min():%d %b %Y} to {days.max():%d %b %Y}. "
           "Answers come only from this data, the weather records and the collected news headlines.")


def show(result):
    st.markdown(result["answer"].replace("$", "\\$"))
    if result["verified"] and result["verified"][1]:
        found, total = result["verified"]
        if found == total:
            st.caption(f"✅ All {total} numbers in this answer were found in the query results.")
        else:
            st.caption(f"⚠️ {found} of {total} numbers in this answer were found in the query results. Check the tables below.")
    if result["steps"]:
        with st.expander(f"How this was answered ({len(result['steps'])} queries)"):
            for number, step in enumerate(result["steps"], start=1):
                st.markdown(f"**{number}. {step['purpose']}**")
                st.code(step["sql"], language="sql")
                if step["error"]:
                    st.error(f"Not run: {step['error']}")
                else:
                    st.dataframe(step["rows"], hide_index=True, width="stretch")


if "chat" not in st.session_state:
    st.session_state.chat = []

if not st.session_state.chat:
    st.markdown("**Try one of these**")
    for column, example in zip(st.columns(len(EXAMPLES)), EXAMPLES):
        if column.button(example, width="stretch"):
            st.session_state.pending = example

for past in st.session_state.chat:
    with st.chat_message("user"):
        st.write(past["question"])
    with st.chat_message("assistant", avatar="✈️"):
        show(past)

question = st.chat_input("Ask a question about the flights") or st.session_state.pop("pending", None)
if question:
    if len(st.session_state.chat) >= QUESTION_LIMIT:
        st.info(f"This visit has reached {QUESTION_LIMIT} questions. Reload the page to start again.")
        st.stop()
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant", avatar="✈️"):
        with st.spinner("Planning queries, checking them, reading the results..."):
            try:
                result = answer_question(question)
            except Exception as error:
                result = {"question": question, "answer": f"Sorry, that did not work: {error}", "steps": [], "verified": None}
        show(result)
    st.session_state.chat.append(result)
