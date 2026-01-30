# Running this Streamlit app:
# ON TERMINAL : streamlit run streamlit_test.py

# app.py - That's the ENTIRE app!
import streamlit as st

st.title("My First Streamlit App")
name = st.text_input("Enter your name:")
if name:
    st.write(f"Hello, {name}!")
