from flask import Flask, render_template_string, request
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime, timedelta

app = Flask(__name__)

def fetch_data(ticker, start_date, end_date, interval):
    """Yahoo Finance에서 데이터를 가져오고 거래량이 없는 날 제거."""
    print(start_date)
    print(end_date)
    data = yf.download(ticker, start=start_date, end=end_date, interval=interval)
    data.columns = data.columns.droplevel(1)
    data = data.dropna()
    # 거래량이 0이거나 없는 날 제거
    data = data[data['Volume'] > 0]

    return data

def preprocess_data(data):
    """데이터 전처리."""
    data['Prev Close'] = data['Close'].shift(1)
    data['Prev Open'] = data['Open'].shift(1)
    data = data.dropna()

    return data

def identify_patterns(data):
    """캔들 패턴 식별."""
    data['Bullish Engulfing'] = (
        (data['Prev Close'] < data['Prev Open']) &
        (data['Close'] > data['Open']) &
        (data['Open'] <= data['Prev Close']) &
        (data['Close'] >= data['Prev Open'])
    )
    data['Bearish Engulfing'] = (
        (data['Prev Close'] > data['Prev Open']) &
        (data['Close'] < data['Open']) &
        (data['Close'] <= data['Prev Open']) &
        (data['Open'] >= data['Prev Close'])
    )
  
    return data

def identify_doji_pattern(data):
    """도지 패턴을 식별."""
    # Doji: 시가와 종가의 차이가 종가의 1% 이하인 경우
    data['Doji'] = abs(data['Close'] - data['Open']) <= data['Close'] * 0.01
    return data

def add_moving_averages(data):
    """이동 평균 계산."""
    for window in [5, 20, 60, 120, 200]:
        data[f'MA{window}'] = data['Close'].rolling(window=window).mean()
    data = data.dropna()
    return data

def create_chart(data, ticker):
    """Plotly를 사용하여 캔들차트를 생성."""

    # 날짜 형식을 문자열로 변환 후 '년-월-일' 형식으로 다시 변환
    data.index = pd.to_datetime(data.index).strftime('%Y-%m-%d')
    
    # 5일 간격으로 날짜 추출
    dates = data.index[::5]
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)

    # 캔들차트 추가
    fig.add_trace(go.Candlestick(
        x=data.index,
        open=data['Open'],
        high=data['High'],
        low=data['Low'],
        close=data['Close'],
        increasing_line_color='red',  # 상승 캔들 색상
        increasing_fillcolor='red',
        increasing_line_width=1,
        decreasing_line_color='blue',
        decreasing_fillcolor='blue',
        decreasing_line_width=1),
        row=1, col=1)

    # 이동 평균 추가
    for ma in ['MA5', 'MA20', 'MA60', 'MA120', 'MA200']:
        fig.add_trace(go.Scatter(x=data.index, y=data[ma], mode='lines', name=ma), row=1, col=1)

    # 거래량 막대 그래프 추가
    data['Volume Color'] = ['red' if data['Volume'].iloc[i] > data['Volume'].iloc[i-1] else 'blue' for i in range(len(data))]
    fig.add_trace(go.Bar(x=data.index, y=data['Volume'], name='Volume', marker=dict(color=data['Volume Color'])), row=2, col=1)

    draw_bull_bear_box(fig, data, 'Bullish Engulfing')
    draw_bull_bear_box(fig, data, 'Bearish Engulfing')

    # 도지 패턴 강조 (노란 박스)
    for i, row in data[data['Doji']].iterrows():
        idx = data.index.get_loc(i)  # 현재 행의 위치 확인
        # 좌우를 포함하기 위해 약간의 여유를 줌
        x0 = data.index[max(idx - 1, 0)]  # 이전 날짜 또는 시작
        print(x0)
        x1 = data.index[min(idx + 1, len(data.index) - 1)]  # 다음 날짜 또는 끝
        fig.add_shape(
            type="rect",
            x0=x0,
            x1=x1,
            y0=row['Low'] * 0.98,  # 박스 아래쪽 경계
            y1=row['High'] * 1.02,  # 박스 위쪽 경계
            line=dict(color="yellow", width=2),
            fillcolor="rgba(255, 255, 0, 0.2)",  # 투명도 20%의 노란색
            name="doji"
        )

    # 레이아웃 업데이트
    fig.update_layout(
        title=f'{ticker} 캔들차트',
        xaxis_title='Date',
        yaxis_title='Price',
        xaxis_rangeslider_visible=False,
        width=1800,
        height=800
    )

    fig.update_xaxes(type='category',
                        tickvals=dates,
                        tickformat='%Y-%m-%d')
    
    return fig.to_html(full_html=False)

def draw_bull_bear_box(fig, data, bull_bear_type):
    draw_type = bull_bear_type
    box_color = 'red'
    rgba = 'rgba(255,0,0,0.2)'

    if(draw_type == 'Bearish Engulfing'):
        box_color = 'blue'
        rgba = 'rgba(0,0,255,0.2)'

    # 상승장악형 박스 추가 (해당 날짜와 전일 포함)
    for i, row in data[data[draw_type]].iterrows():
        # 현재 날짜와 전일 날짜
        current_date = i
        prev_date = data.index[data.index.get_loc(i) - 1]  # 전일 인덱스


        # 유격을 위한 여유 비율 설정
        margin_ratio = 0.05  # 5% 유격

        # 박스의 y0와 y1 계산 (상하 유격 추가)
        box_low = min(data.loc[prev_date, 'Low'], row['Low']) * (1 - margin_ratio)
        box_high = max(data.loc[prev_date, 'High'], row['High']) * (1 + margin_ratio)

        # 박스의 x0와 x1 계산 (좌우 유격 추가)
        x_margin = 1  # 날짜의 간격을 기준으로 여유 공간 추가
        x0 = data.index[max(data.index.get_loc(prev_date) - x_margin, 0)]
        x1 = data.index[min(data.index.get_loc(current_date) + x_margin, len(data.index) - 1)]


        # 박스의 y0와 y1 계산
        box_low = min(data.loc[prev_date, 'Low'], row['Low'])  # 전일과 현재의 Low 값 중 더 낮은 값
        box_high = max(data.loc[prev_date, 'High'], row['High'])  # 전일과 현재의 High 값 중 더 높은 값

        # 박스 추가
        fig.add_shape(
                        type="rect",
                        x0=x0,
                        x1=x1,
                        y0=box_low,
                        y1=box_high,
                        line=dict(color=box_color, width=1),
                        fillcolor=rgba 
        )

@app.route('/', methods=['GET', 'POST'])
def home():
    today = datetime.now()
    startdate = today - timedelta(days=30)
    ticker = 'RGTI'
    start_date = startdate.strftime('%Y-%m-%d')
    end_date = today.strftime('%Y-%m-%d')

    if request.method == 'POST':
        ticker = request.form['ticker']
        start_date = request.form['start_date']
        end_date = request.form['end_date']
        interval = request.form['interval']  # 사용자가 선택한 간격

        data = fetch_data(ticker, start_date, end_date, interval)
        print('####################1')
        print(data)
        if not data.empty:
            data = preprocess_data(data)
            print('####################2')
            print(data)
            data = identify_patterns(data)
            data = identify_doji_pattern(data)  # 도지 패턴 식별
            print('####################3')
            print(data)
            data = add_moving_averages(data)
            print('####################4444')
            print(data)
            chart_html = create_chart(data, ticker)
        else:
            chart_html = "<h3>No data found for the selected criteria.</h3>"
    else:
        chart_html = "<h3>Please enter search criteria and submit.</h3>"

    return render_template_string('''
         <!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>캔들분석</title>
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-3.5.1.min.js"></script>
</head>
<body class="bg-light">

    <!-- 네비게이션 바 -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="#">📈캔들분석/a>
        </div>
    </nav>

    <!-- 메인 컨테이너 -->
    <div class="container mt-5">
        <h1 class="text-center mb-4">캔들차트 조회</h1>

        <!-- 입력 폼 -->
        <div class="card shadow-sm mb-4">
            <div class="card-body">
                <form method="POST" class="row g-3">
                    <div class="col-md-6">
                        <label class="form-label">티커 (Ticker)</label>
                        <input type="text" class="form-control" name="ticker" value="{{ ticker }}" required>
                    </div>
                    <div class="col-md-6">
                        <label class="form-label">간격 (Interval)</label>
                        <select class="form-select" name="interval">
                            <option value="1m">1분</option>
                            <option value="5m">5분</option>
                            <option value="15m">15분</option>
                            <option value="30m">30분</option>
                            <option value="60m">1시간</option>
                            <option value="1d" selected>1일</option>
                            <option value="1wk">1주</option>
                            <option value="1mo">1개월</option>
                        </select>
                    </div>
                    <div class="col-md-6">
                        <label class="form-label">조회 시작일 (Start Date)</label>
                        <input type="date" class="form-control" name="start_date" value="{{ start_date }}" required>
                    </div>
                    <div class="col-md-6">
                        <label class="form-label">조회 종료일 (End Date)</label>
                        <input type="date" class="form-control" name="end_date" value="{{ end_date }}" required>
                    </div>
                    <div class="col-12 text-center mt-3">
                        <button type="submit" class="btn btn-primary btn-lg">조회</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- 차트 영역 -->
        <div class="card shadow-sm">
            <div class="card-body">
                <h5 class="card-title">📊 캔들차트</h5>
                <div id="chart">{{ chart_html | safe }}</div>
            </div>
        </div>
    </div>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
    ''', ticker=ticker, start_date=start_date, end_date=end_date, chart_html=chart_html)

if __name__ == '__main__':
    app.run(debug=True)