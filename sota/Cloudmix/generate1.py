import numpy as np
import random
import math
import pandas as pd

ranks = [i for i in range(2,86,2)]
mem_size = [i for i in range(1,17)]
stride = [1,2,3,4,5,6]

params = [

]

for i1 in mem_size:
    for i2 in stride:
        params.append([[1,'mem', 2500000000, i2, i1 * 1024]])

'''for i1 in ranks:
    params.append([[i1,'div', 5000000000]])
    params.append([[i1,'add', 25000000000]])'''


results = [
    {
        "param_set":item
    }
    for item in params
]
result_df = pd.DataFrame(results)

result_df.to_csv('param_sets.csv', index=False)