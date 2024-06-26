import os

import numpy as np
import torch
import backbone
import configs
from io_utils import parse_args_regression
from methods.DKT_regression import DKT
from methods.feature_transfer_regression import FeatureTransfer

params = parse_args_regression("train_regression")
np.random.seed(params.seed)
torch.manual_seed(params.seed)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

params.checkpoint_dir = "%scheckpoints/%s/" % (configs.save_dir, params.dataset)
if not os.path.isdir(params.checkpoint_dir):
    os.makedirs(params.checkpoint_dir)
params.checkpoint_dir = "%scheckpoints/%s/%s_%s" % (
    configs.save_dir,
    params.dataset,
    params.model,
    params.method,
)

bb = backbone.Conv3()

if params.method == "DKT":
    model = DKT(bb)
elif params.method == "transfer":
    model = FeatureTransfer(bb)
else:
    raise ValueError("Unrecognised method")

optimizer = torch.optim.Adam(
    [
        {"params": model.model.parameters(), "lr": 0.001},
        {"params": model.feature_extractor.parameters(), "lr": 0.001},
    ]
)

for epoch in range(params.stop_epoch):
    model.train_loop(epoch, optimizer)

model.save_checkpoint(params.checkpoint_dir)
