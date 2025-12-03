import io
import math
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

# Set the title and favicon that appear in the Browser's tab bar.
st.set_page_config(
    page_title='GDP dashboard',
    page_icon=':earth_americas:', # This is an emoji shortcode. Could be a URL too.
)

# -----------------------------------------------------------------------------
# Declare some useful functions.

@st.cache_data
def get_gdp_data():
    """Grab GDP data from a CSV file.

    This uses caching to avoid having to read the file every time. If we were
    reading from an HTTP endpoint instead of a file, it's a good idea to set
    a maximum age to the cache with the TTL argument: @st.cache_data(ttl='1d')
    """

    # Instead of a CSV on disk, you could read from an HTTP endpoint here too.
    DATA_FILENAME = Path(__file__).parent/'data/gdp_data.csv'
    raw_gdp_df = pd.read_csv(DATA_FILENAME)

    MIN_YEAR = 1960
    MAX_YEAR = 2022

    # The data above has columns like:
    # - Country Name
    # - Country Code
    # - [Stuff I don't care about]
    # - GDP for 1960
    # - GDP for 1961
    # - GDP for 1962
    # - ...
    # - GDP for 2022
    #
    # ...but I want this instead:
    # - Country Name
    # - Country Code
    # - Year
    # - GDP
    #
    # So let's pivot all those year-columns into two: Year and GDP
    gdp_df = raw_gdp_df.melt(
        ['Country Code'],
        [str(x) for x in range(MIN_YEAR, MAX_YEAR + 1)],
        'Year',
        'GDP',
    )

    # Convert years from string to integers
    gdp_df['Year'] = pd.to_numeric(gdp_df['Year'])

    return gdp_df

gdp_df = get_gdp_data()


def parse_contact_csv(uploaded_file: io.BytesIO) -> pd.DataFrame:
    """Read and normalize a CSV file containing URLs for contact forms."""
    df = pd.read_csv(uploaded_file)
    normalized_columns = {col: col.strip().lower() for col in df.columns}
    df = df.rename(columns=normalized_columns)

    if 'url' not in df.columns:
        raise ValueError('CSV needs a column named "url" that lists contact form links.')

    return df[['url']].dropna().reset_index(drop=True)


def validate_url(url: str) -> bool:
    """Return True if the URL appears valid enough for a simulated submission."""
    parsed = urlparse(url)
    return bool(parsed.scheme and parsed.netloc)


def simulate_submissions(urls: pd.Series, payload: dict) -> pd.DataFrame:
    """Simulate submitting a template payload to each URL."""
    results = []

    for index, url in urls.items():
        if not validate_url(url):
            status = '失敗'
            detail = 'URLを認識できませんでした'
        elif not payload['message']:
            status = '失敗'
            detail = '問い合わせ内容が未入力です'
        else:
            status = '成功(デモ)'
            detail = '外部送信は行わずに結果のみ記録しました'

        results.append({
            'No.': index + 1,
            'URL': url,
            '結果': status,
            '詳細': detail,
            '送信者': payload['name'],
            'メール': payload['email'],
        })

    return pd.DataFrame(results)

st.title(':earth_americas: GDP dashboard & 問い合わせ送信デモ')

overview, contact_tab = st.tabs(['GDP dashboard', '問い合わせ送信デモ'])

with overview:
    st.markdown('''
    Browse GDP data from the [World Bank Open Data](https://data.worldbank.org/) website. As you'll
    notice, the data only goes to 2022 right now, and datapoints for certain years are often missing.
    But it's otherwise a great (and did I mention _free_?) source of data.
    ''')

    # Add some spacing
    ''
    ''

    min_value = gdp_df['Year'].min()
    max_value = gdp_df['Year'].max()

    from_year, to_year = st.slider(
        'Which years are you interested in?',
        min_value=min_value,
        max_value=max_value,
        value=[min_value, max_value])

    countries = gdp_df['Country Code'].unique()

    if not len(countries):
        st.warning("Select at least one country")

    selected_countries = st.multiselect(
        'Which countries would you like to view?',
        countries,
        ['DEU', 'FRA', 'GBR', 'BRA', 'MEX', 'JPN'])

    ''
    ''
    ''

    # Filter the data
    filtered_gdp_df = gdp_df[
        (gdp_df['Country Code'].isin(selected_countries))
        & (gdp_df['Year'] <= to_year)
        & (from_year <= gdp_df['Year'])
    ]

    st.header('GDP over time', divider='gray')

    ''

    st.line_chart(
        filtered_gdp_df,
        x='Year',
        y='GDP',
        color='Country Code',
    )

    ''
    ''


    first_year = gdp_df[gdp_df['Year'] == from_year]
    last_year = gdp_df[gdp_df['Year'] == to_year]

    st.header(f'GDP in {to_year}', divider='gray')

    ''

    cols = st.columns(4)

    for i, country in enumerate(selected_countries):
        col = cols[i % len(cols)]

        with col:
            first_gdp = first_year[first_year['Country Code'] == country]['GDP'].iat[0] / 1000000000
            last_gdp = last_year[last_year['Country Code'] == country]['GDP'].iat[0] / 1000000000

            if math.isnan(first_gdp):
                growth = 'n/a'
                delta_color = 'off'
            else:
                growth = f'{last_gdp / first_gdp:,.2f}x'
                delta_color = 'normal'

            st.metric(
                label=f'{country} GDP',
                value=f'{last_gdp:,.0f}B',
                delta=growth,
                delta_color=delta_color
            )

with contact_tab:
    st.subheader('CSVアップロードと定型文入力')
    st.caption('外部サイトへの実送信は行わず、送信処理をシミュレーションします。URLが無効な場合や本文が未入力の場合は失敗として扱います。')

    uploaded_file = st.file_uploader('問い合わせフォームのURL一覧CSVをアップロード', type='csv')

    default_message = '平素より大変お世話になっております。貴社サービスについてお伺いしたく、ご連絡いたしました。'

    with st.form('contact_form'):
        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input('お名前*', max_chars=100)
            email = st.text_input('メールアドレス*', max_chars=200)
            company = st.text_input('会社名 / 部署', max_chars=200)
        with col2:
            subject = st.text_input('件名*', max_chars=150, value='お問い合わせのご連絡')
            phone = st.text_input('電話番号', max_chars=50)
            agree = st.checkbox('個人情報取り扱いに同意します*', value=True)

        message = st.text_area('問い合わせ内容*', value=default_message, height=180)
        submitted = st.form_submit_button('定型文を送信（デモ）')

    payload = {
        'name': name,
        'email': email,
        'company': company,
        'phone': phone,
        'subject': subject,
        'message': message,
        'agree': agree,
    }

    if submitted:
        if uploaded_file is None:
            st.error('送信にはURL一覧のCSVが必要です。')
        elif not all([payload['name'], payload['email'], payload['subject'], payload['message'], payload['agree']]):
            st.error('必須項目（同意含む）をすべて入力してください。')
        else:
            try:
                contact_df = parse_contact_csv(uploaded_file)
                results_df = simulate_submissions(contact_df['url'], payload)
                st.success('送信シミュレーションが完了しました。結果をご確認ください。')
                st.dataframe(results_df, use_container_width=True)

                csv_buffer = io.StringIO()
                results_df.to_csv(csv_buffer, index=False)
                st.download_button(
                    '結果をCSVでダウンロード',
                    data=csv_buffer.getvalue(),
                    file_name='contact_results.csv',
                    mime='text/csv'
                )
            except ValueError as error:
                st.error(str(error))
