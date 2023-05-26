from dash import Dash, html, dcc, callback, Output, Input
import plotly.express as px
import pandas as pd

from pathlib import Path
from tkinter.filedialog import askdirectory

from martin_binance import BACKTEST_PATH

colors = {'background': '#696969',
          'text': '#7FDBFF'}

# df_path = askdirectory(title='Pick a folder', initialdir=str(BACKTEST_PATH))

df_path = Path('/home/ubuntu/.MartinBinance/back_test/BTCUSDT_0526-17:50:17')

ds_ticker = pd.read_pickle(Path(BACKTEST_PATH, df_path, "ticker.pkl"))
df_grid_sell = pd.read_pickle(Path(BACKTEST_PATH, df_path, "sell.pkl"))
df_grid_buy = pd.read_pickle(Path(BACKTEST_PATH, df_path, "buy.pkl"))

app = Dash(__name__)

fig=px.line(ds_ticker)

fig.update_layout(paper_bgcolor="#ddd")
fig.update_layout(plot_bgcolor="#ccc")

app.layout = html.Div(
    [html.H2(children='Back test data analyser',
             style={'textAlign': 'center', 'color': colors['text'], 'backgroundColor': colors['background']}),
    dcc.Graph(figure=fig)])


if __name__ == '__main__':
    app.run_server(debug=True)


'''
app.layout = html.Div([
    html.H1(children='Back test data analyser', style={'textAlign':'center'}),
    dcc.Dropdown(df.country.unique(), 'Canada', id='dropdown-selection'),
    dcc.Graph(id='graph-content')
])

@callback(
    Output('graph-content', 'figure'),
    Input('dropdown-selection', 'value')
)
def update_graph(value):
    dff = df[df.country==value]
    return px.line(dff, x='year', y='pop')

if __name__ == '__main__':
    app.run_server(debug=True)
'''