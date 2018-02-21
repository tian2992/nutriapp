from .models import Visit, Metric

def fetch_historical_metrics(person_id):
    visits = Visit.objects.filter(patient=person_id)
    metrics = {}
    for v in visits:
        mets = Metric.objects.filter(visit=v)
        metrics[v.date] = list(mets)

    return metrics
