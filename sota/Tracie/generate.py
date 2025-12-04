import numpy as np
import random
import math
import pandas as pd
results = [
    {
        "params":['backprop', '100000000']
    }
]
result_df = pd.DataFrame(results)

result_df.to_csv('param_sets.csv', index=False)