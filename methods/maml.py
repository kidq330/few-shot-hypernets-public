# This code is modified from https://github.com/dragen1860/MAML-Pytorch and https://github.com/katerakelly/pytorch-maml

from time import time

import numpy as np
import torch
from torch import nn

import backbone
from methods.meta_template import MetaTemplate


class MAML(MetaTemplate):
    def __init__(self, model_func, n_way, n_support, n_query, params, approx=False):
        super().__init__(model_func, n_way, n_support, n_query, change_way=False)

        self.loss_fn = nn.CrossEntropyLoss()
        self.classifier = backbone.Linear_fw(self.feat_dim, n_way)
        self.classifier.bias.data.fill_(0)

        self.maml_adapt_classifier = params.maml_adapt_classifier

        self.n_task = 4
        self.task_update_num = 5
        self.train_lr = 0.01
        self.approx = approx  # first order approx.

    def forward(self, x):
        out = self.feature.forward(x)
        scores = self.classifier.forward(out)
        return scores

    def set_forward(self, x, is_feature=False):
        assert is_feature is False, "MAML does not support fixed feature"
        x_a_i = (
            x[:, : self.n_support, :, :, :]
            .contiguous()
            .view(self.n_way * self.n_support, *x.size()[2:])
            .to(self.device)
        )  # support data
        x_b_i = (
            x[:, self.n_support :, :, :, :]
            .contiguous()
            .view(self.n_way * self.n_query, *x.size()[2:])
            .to(self.device)
        )  # query data
        y_a_i = torch.repeat_interleave(torch.arange(self.n_way), self.n_support).to(
            self.device, dtype=torch.long
        )  # label for support data

        if self.maml_adapt_classifier:
            fast_parameters = list(self.classifier.parameters())
            for weight in self.classifier.parameters():
                weight.fast = None
        else:
            fast_parameters = list(
                self.parameters()
            )  # the first gradient calcuated in line 45 is based on original weight
            for weight in self.parameters():
                weight.fast = None

        self.zero_grad()

        for _task_step in range(self.task_update_num):
            scores = self.forward(x_a_i)
            set_loss = self.loss_fn(scores, y_a_i)
            grad = torch.autograd.grad(
                set_loss, fast_parameters, create_graph=True
            )  # build full graph support gradient of gradient
            if self.approx:
                grad = [
                    g.detach() for g in grad
                ]  # do not calculate gradient of gradient if using first order approximation
            fast_parameters = []
            parameters = (
                self.classifier.parameters()
                if self.maml_adapt_classifier
                else self.parameters()
            )
            for k, weight in enumerate(parameters):
                # for usage of weight.fast, please see Linear_fw, Conv_fw in backbone.py
                if weight.fast is None:
                    weight.fast = weight - self.train_lr * grad[k]  # create weight.fast
                else:
                    weight.fast = (
                        weight.fast - self.train_lr * grad[k]
                    )  # create an updated weight.fast, note the '-' is not merely minus value, but to create a new weight.fast
                fast_parameters.append(
                    weight.fast
                )  # gradients calculated in line 45 are based on newest fast weight, but the graph will retain the link to old weight.fasts

        scores = self.forward(x_b_i)
        return scores

    def set_forward_adaptation(self, x, is_feature=False):  # overwrite parrent function
        raise ValueError(
            "MAML performs further adapation simply by increasing task_upate_num"
        )

    def set_forward_loss(self, x):
        scores = self.set_forward(x, is_feature=False)
        query_data_labels = torch.repeat_interleave(
            torch.arange(self.n_way), self.n_query
        ).to(self.device, dtype=torch.long)
        loss = self.loss_fn(scores, query_data_labels)

        _topk_scores, topk_labels = scores.data.topk(1, 1, True, True)
        topk_ind = topk_labels.flatten()
        y_labels = query_data_labels
        top1_correct = torch.sum(topk_ind == y_labels)
        task_accuracy = (top1_correct / len(query_data_labels)) * 100

        return dict(loss=loss, task_accuracy=task_accuracy)

    def train_loop(self, epoch, train_loader, optimizer):  # overwrite parrent function
        print_freq = 10
        avg_loss = 0
        task_count = 0
        loss_all = []
        acc_all = []
        optimizer.zero_grad()

        # train
        for i, (x, _) in enumerate(train_loader):
            self.n_query = x.size(1) - self.n_support
            assert self.n_way == x.size(0), "MAML do not support way change"

            loss, task_accuracy = self.set_forward_loss(x)
            avg_loss = avg_loss + loss.item()  # .data[0]
            loss_all.append(loss)
            acc_all.append(task_accuracy)

            task_count += 1

            if task_count == self.n_task:  # MAML update several tasks at one time
                loss_q = torch.stack(loss_all).sum(0)
                loss_q.backward()

                optimizer.step()
                task_count = 0
                loss_all = []
            optimizer.zero_grad()
            if i % print_freq == 0:
                print(
                    "Epoch {:d} | Batch {:d}/{:d} | Loss {:f}".format(
                        epoch, i, len(train_loader), avg_loss / float(i + 1)
                    )
                )

        acc_all = np.asarray(acc_all)
        acc_mean = np.mean(acc_all)

        metrics = {"accuracy/train": acc_mean}

        return metrics

    def test_loop(
        self, test_loader, return_std=False, return_time: bool = False
    ):  # overwrite parrent function
        _correct = 0
        _count = 0
        acc_all = []
        eval_time = 0
        iter_num = len(test_loader)
        for _i, (x, _) in enumerate(test_loader):
            self.n_query = x.size(1) - self.n_support
            assert self.n_way == x.size(0), "MAML do not support way change"
            s = time()
            correct_this, count_this = self.correct(x)
            t = time()
            eval_time += t - s
            acc_all.append(correct_this / count_this * 100)

        num_tasks = len(acc_all)
        acc_all = np.asarray(acc_all)
        acc_mean = np.mean(acc_all)
        acc_std = np.std(acc_all)
        print(
            "%d Test Acc = %4.2f%% +- %4.2f%%"
            % (iter_num, acc_mean, 1.96 * acc_std / np.sqrt(iter_num))
        )
        print("Num tasks", num_tasks)

        ret = [acc_mean]
        if return_std:
            ret.append(acc_std)
        if return_time:
            ret.append(eval_time)
        ret.append({})

        return ret

    # used in regression
    def get_logits(self, x):
        self.n_query = x.size(1) - self.n_support
        logits = self.set_forward(x)
        return logits
