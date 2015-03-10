#!/usr/bin/env python
# coding=utf-8
from __future__ import division, print_function, unicode_literals
from brainstorm.utils import get_inheritors


class LayerBase(object):
    """
    The base-class of all layer types defined in Python.
    """

    def __init__(self, size, in_size, sink_layers, source_layers, kwargs):
        self.in_size = in_size
        self.validate_kwargs(kwargs)
        self.kwargs = kwargs
        self.out_size = self._get_output_size(size, in_size, kwargs)
        self.sink_layers = sink_layers
        self.source_layers = source_layers
        self.handler = None

    def set_handler(self, new_handler):
        """
        A function that is called to set a new handler and then do some
        follow-up operations.
        For example, it may be used to reset activation functions.
        It may also be used to restrict the layer to certain handlers.
        """
        self.handler = new_handler

    @classmethod
    def validate_kwargs(cls, kwargs):
        assert not kwargs, "Unexpected kwargs: {}".format(list(kwargs.keys()))

    @classmethod
    def _get_output_size(cls, size, in_size, kwargs):
        return size if size is not None else in_size

    def get_parameter_structure(self):
        return []

    def forward_pass(self, parameters, input_buffer, output_buffer):
        pass

    def backward_pass(self, parameters, input_buffer, output_buffer,
                      in_delta_buffer, out_delta_buffer, gradient_buffer):
        pass


class InputLayer(LayerBase):
    """
    Special input layer type.
    """

    def __init__(self, size, in_size, sink_layers, source_layers, kwargs):
        super(InputLayer, self).__init__(size, in_size, sink_layers,
                                         source_layers, kwargs)
        assert not in_size, "InputLayer cannot have an in_size"


class NoOpLayer(LayerBase):
    """
    This layer just copies its input into its output.
    """

    def __init__(self, size, in_size, sink_layers, source_layers, kwargs):
        super(NoOpLayer, self).__init__(size, in_size, sink_layers,
                                        source_layers, kwargs)
        assert size == in_size, "For NoOpLayer in and out size must be equal"


class FeedForwardLayer(LayerBase):
    def __init__(self, size, in_size, sink_layers, source_layers, kwargs):
        super(FeedForwardLayer, self).__init__(size, in_size, sink_layers,
                                               source_layers, kwargs)
        self.act_func = None
        self.act_func_deriv = None
        self.kwargs = kwargs

    def set_handler(self, new_handler):
        self.handler = new_handler

        # Assign act_func and act_dunc_derivs
        activation_functions = {
            'sigmoid': (self.handler.sigmoid, self.handler.sigmoid_deriv),
            'tanh': (self.handler.tanh, self.handler.tanh_deriv),
            'linear': (lambda x: x, 1),
            'rel': (self.handler.rel, self.handler.rel_deriv)
        }

        self.act_func, self.act_func_deriv = \
            activation_functions[self.kwargs.get('act_func', 'tanh')]

    @classmethod
    def validate_kwargs(cls, kwargs):
        for key in kwargs.keys():
            assert key in ['act_func'], "Unexpected kwarg: {} for " \
                                        "FeedForwardLayer".format(key)

    def get_parameter_structure(self):
        return [
            ('W', (self.in_size, self.out_size)),
            ('b', self.out_size)
        ]

    def forward_pass(self, parameters, input_buffer, output_buffer):

        # prepare
        H = self.handler
        WX, W_bias = parameters['W'], parameters['b']

        # reshape
        t, b, f = input_buffer.shape
        flat_input = H.reshape(input_buffer, (t * b, f))
        flat_output = H.reshape(output_buffer, (t * b, self.out_size))

        # calculate outputs
        H.dot(flat_input, WX, flat_output)
        H.add_mv(flat_output, W_bias, flat_output)
        self.act_func(flat_output, flat_output)

    def backward_pass(self, parameters, input_buffer, output_buffer,
                      in_delta_buffer, out_delta_buffer, gradient_buffer):

        # prepare
        H = self.handler
        WX, W_bias = parameters['W'], parameters['b']
        dWX, dW_bias = gradient_buffer['W'], gradient_buffer['b']
        dZ = H.zeros(output_buffer.shape)

        # reshape
        t, b, f = input_buffer.shape
        flat_input = H.reshape(input_buffer, (t * b, f))
        flat_dZ = H.reshape(dZ, (t * b, self.out_size))
        flat_in_delta_buffer = H.reshape(in_delta_buffer, (t * b, f))

        # calculate in deltas and gradients
        self.act_func_deriv(None, output_buffer, out_delta_buffer, dZ)
        H.dot_add(flat_dZ, WX.T, flat_in_delta_buffer)
        H.dot(flat_input.T, flat_dZ, dWX)
        H.sum(flat_dZ, axis=0, out=dW_bias)


def get_layer_class_from_typename(typename):
    layer_classes = get_inheritors(LayerBase)
    for layer_class in layer_classes:
        if typename == layer_class.__name__:
            return layer_class
    else:
        raise TypeError("Layer-type '{}' unknown!".format(typename))
