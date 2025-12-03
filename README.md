# :earth_americas: GDP dashboard template

A simple Streamlit app showing the GDP of different countries in the world.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://gdp-dashboard-template.streamlit.app/)

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```

### Contact form batch demo

The app now includes a "問い合わせ送信デモ" tab that walks through uploading a CSV of contact form URLs, filling in a reusable message, and downloading a simulated result log.

1. Prepare a CSV that contains a `url` column with the destinations you want to test.
2. Open the tab, upload the CSV, and fill in the required fields (name, email, subject, and inquiry text).
3. Click the submission button to run the simulation and review the success/failure results.
4. Download the results as a CSV for record keeping.
