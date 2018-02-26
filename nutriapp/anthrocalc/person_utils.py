from .models import Visit, Metric

def fetch_historical_metrics(person_id):
    visits = Visit.objects.filter(patient=person_id)
    metrics = {}
    for v in visits:
        try:
            mets = Metric.objects.filter(visit=v)[0]
        except:
            mets = None
        metrics[v.id] = {"date": v.date, "metrics": mets}

    return metrics

def calculate_indexes():
    pass
