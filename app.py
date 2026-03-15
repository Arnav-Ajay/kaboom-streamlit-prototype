import streamlit as st

from src.ui.views import game_page, landing_page


def main() -> None:
    st.set_page_config(page_title="Kaboom Streamlit", page_icon="K", layout="wide")

    if "page" not in st.session_state:
        st.session_state.page = "landing"

    if st.session_state.page == "game":
        game_page()
        return

    landing_page()


if __name__ == "__main__":
    main()
