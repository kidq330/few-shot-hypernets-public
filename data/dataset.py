# This code is modified from https://github.com/facebookresearch/low-shot-shrink-hallucinate

from collections import defaultdict
import torch
from PIL import Image
import json
import numpy as np
import torchvision.transforms as transforms
import os

from torch.utils.data import Dataset, DataLoader

identity = lambda x: x


class SimpleDataset:
    def __init__(self, data_file, transform, target_transform=identity):
        with open(data_file, "r", encoding="utf-8") as f:
            self.meta = json.load(f)
        self.transform = transform
        self.target_transform = target_transform

    def __getitem__(self, i):
        image_path = os.path.join(self.meta["image_names"][i])
        img = Image.open(image_path).convert("RGB")
        img = self.transform(img)
        target = self.target_transform(self.meta["image_labels"][i])
        return img, target

    def __len__(self):
        return len(self.meta["image_names"])


class SetDataset(Dataset):
    def __init__(self, data_file, batch_size, transform):
        with open(data_file, "r", encoding="utf-8") as f:
            self.meta = json.load(f)

        self.cl_list = np.unique(self.meta["image_labels"]).tolist()

        self.sub_meta = defaultdict(list)
        for x, y in zip(self.meta["image_names"], self.meta["image_labels"]):
            self.sub_meta[y].append(x)

        self.sub_dataloader = []
        sub_data_loader_params = dict(
            batch_size=batch_size,
            shuffle=True,
            num_workers=0,  # use main thread only or may receive multiple batches
            pin_memory=False,
        )

        print({len(y) for y in self.sub_meta.values()})
        for cl in self.cl_list:
            sub_dataset = SubDataset(self.sub_meta[cl], cl, transform=transform)
            self.sub_dataloader.append(
                DataLoader(sub_dataset, **sub_data_loader_params)
            )

    def __getitem__(self, i):
        return next(iter(self.sub_dataloader[i]))

    def __len__(self):
        return len(self.cl_list)  # number of classes in dataset


class SubDataset(Dataset):
    def __init__(
        self, sub_meta, cl, transform=transforms.ToTensor(), target_transform=identity
    ):
        self.sub_meta = sub_meta
        self.cl = cl
        self.transform = transform
        self.target_transform = target_transform

    def __getitem__(self, i):
        # print( '%d -%d' %(self.cl,i))
        image_path = os.path.join(self.sub_meta[i])
        img = Image.open(image_path).convert("RGB")
        img = self.transform(img)
        target = self.target_transform(self.cl)
        return img, target

    def __len__(self):
        return len(self.sub_meta)


class EpisodicBatchSampler:
    def __init__(self, n_classes, n_way, n_episodes):
        self.n_classes = n_classes
        self.n_way = n_way
        self.n_episodes = n_episodes

    def __len__(self):
        return self.n_episodes

    def __iter__(self):
        for _i in range(self.n_episodes):  # why is this iterable finite __jm__
            yield torch.randperm(self.n_classes)[: self.n_way]
