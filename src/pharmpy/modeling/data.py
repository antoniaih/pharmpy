# Functional interface to extract dataset information


def ninds(model):
    """Retrieve the number of individuals in the model dataset"""
    return model.dataset.pharmpy.ninds


def nobs(model):
    """Retrieve the total number of observations in the model dataset"""
    return model.dataset.pharmpy.nobs
