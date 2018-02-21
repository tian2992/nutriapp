from .models import *
import django
import random
import datetime
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.dates import DateFormatter

from .person_utils import fetch_historical_metrics

def graph_for_person(request):
    person_id = int(request.GET["person_id"])
    metrics = fetch_historical_metrics(person_id)
    print(metrics)
    ## TODO: calculate & plot

    response=django.http.HttpResponse(content_type='image/png')

    return response


def simple(request):
    fig=Figure()
    ax=fig.add_subplot(111)
    x=[]
    y=[]
    now=datetime.datetime.now()
    delta=datetime.timedelta(days=1)
    for i in range(10):
        x.append(now)
        now+=delta
        y.append(random.randint(0, 1000))
    ax.plot_date(x, y, '-')
    ax.xaxis.set_major_formatter(DateFormatter('%Y-%m-%d'))
    fig.autofmt_xdate()
    canvas=FigureCanvas(fig)
    response=django.http.HttpResponse(content_type='image/png')
    canvas.print_png(response)
    return response
