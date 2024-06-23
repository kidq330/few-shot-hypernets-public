from typing import Optional
from torch import Tensor
import torch.nn as nn
import re
import warnings

from collections import OrderedDict
from torch.nn.parameter import Parameter

MetaParamDict = OrderedDict[str, Tensor]


class MetaModule(nn.Module):
    """
    Base class for PyTorch meta-learning modules. These modules accept an
    additional argument `params` in their `forward` method.
    self.forward(x) === self.forward(x, params=dict(self.meta_named_parameters()))

    Notes
    -----
    Objects inherited from `MetaModule` are fully compatible with PyTorch
    modules from `torch.nn.Module`. The argument `params` is a dictionary of
    tensors, with full support of the computation graph (for differentiation).
    """

    def __init__(self):
        super(MetaModule, self).__init__()
        self._children_modules_parameters_cache = dict()

    def meta_named_parameters(self, prefix='', recurse=True):
        gen = self._named_members(
            lambda module: module._parameters.items()
            if isinstance(module, MetaModule) else [],
            prefix=prefix, recurse=recurse)
        for elem in gen:
            yield elem

    def meta_parameters(self, recurse=True):
        for name, param in self.meta_named_parameters(recurse=recurse):
            yield param

    def get_subdict(self, params, key=None):
        if params is None:
            return None
        all_names = tuple(params.keys())
        if (key, all_names) not in self._children_modules_parameters_cache:
            if key is None:
                self._children_modules_parameters_cache[(
                    key, all_names)] = all_names

            else:
                key_escape = re.escape(key)
                key_re = re.compile(r'^{0}\.(.+)'.format(key_escape))

                self._children_modules_parameters_cache[(key, all_names)] = [
                    key_re.sub(r'\1', k) for k in all_names if key_re.match(k) is not None]

        names = self._children_modules_parameters_cache[(key, all_names)]
        if not names:
            warnings.warn(
                f"""Module `{self.__class__.__name__}` has no parameter corresponding to the submodule named `{key}`
                    in the dictionary `params` provided as an argument to `forward()`.
                    Using the default parameters for this submodule. The list of the parameters in `params`: {all_names}.""",
                stacklevel=2)
            return None

        return OrderedDict([(name, params[f'{key}.{name}']) for name in names])

    def merge_subdict(self, params: Optional[OrderedDict[str, Tensor]], key=None):
        """
            TODO: docstring
        """

        # assert set(params.keys()) == set(self.get_subdict(self.meta_named_parameters(), key)) # contract
        # this means params must be a valid subdict of self
        mnp = OrderedDict(self.meta_named_parameters())
        if params is None:
            return mnp

        canonical_param_names = [f"{key}.{name}" for name in params.keys()]
        # assert set(canonical_param_names).issubset(set(mnp.keys()))

        mnp.update(zip(
            canonical_param_names,
            params.values(),
        ))
        return mnp
