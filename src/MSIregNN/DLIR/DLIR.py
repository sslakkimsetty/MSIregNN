import tensorflow as tf
import numpy as np
from tensorflow.keras.models import Sequential
from tensorflow.keras import layers
from tensorflow.keras.layers import Dense, Dropout, Conv2D, Reshape, Flatten, MaxPooling2D
from ..stn_bspline import SpatialTransformerBspline




class Linear(layers.Layer):

    def __init__(self, units=32, input_dim=32,
        is_transformer_regressor=False):
        super(Linear, self).__init__()

        if is_transformer_regressor:
            w_init = tf.zeros_initializer()
            theta = np.zeros(shape=(units,))
            theta = tf.cast(theta, "float32")
            self.b = tf.Variable(initial_value=theta, trainable=True)
        else:
            w_init = tf.random_normal_initializer()
            b_init = tf.zeros_initializer()
            self.b = tf.Variable(initial_value=b_init(
                shape=(units,),
                dtype="float32"
                ), trainable=True)

        self.w = tf.Variable(initial_value=w_init(shape=(input_dim, units),
                                                  dtype="float32"), trainable=True)

    def call(self, inputs):
        return tf.matmul(inputs, self.w) + self.b



class LocNet(tf.keras.layers.Layer):

    def __init__(self):
        super(LocNet, self).__init__()

        self.conv1 = Conv2D(filters=8, kernel_size=7, activation="relu")
        self.maxpool1 = MaxPooling2D(pool_size=(2,2), strides=2)
        self.conv2 = Conv2D(filters=10, kernel_size=5, activation="relu")
        self.maxpool2 = MaxPooling2D(pool_size=(2,2), strides=2)

    def call(self, inputs):
        x = self.conv1(inputs)
        x = self.maxpool1(x)
        x = self.conv2(x)
        x = self.maxpool2(x)
        return x



class TransformationRegressor(tf.keras.layers.Layer):

    def __init__(self, theta_units=6, input_dim=None):
        super(TransformationRegressor, self).__init__()

        self.linear1 = Linear(units=theta_units*5, input_dim=input_dim)
        self.linear2 = Linear(units=theta_units, input_dim=theta_units*5,
                              is_transformer_regressor=True)

    def call(self, inputs):
        x = self.linear1(inputs)
        x = tf.nn.tanh(x)
        x = self.linear2(x)
        x = tf.nn.tanh(x)
        return x



class DLIR(tf.keras.models.Model):

    def __init__(self, drate=0.2, grid_res=None, img_res=None,
        input_dim=None):
        super(DLIR, self).__init__()
        self.grid_res = grid_res
        self.img_res = img_res
        self.drate = drate
        self.B = 1

        self.loc_net = LocNet()
        self.flatten = Flatten()
        self.transformer = SpatialTransformerBspline(img_res=self.img_res,
                                                     grid_res=self.grid_res,
                                                     out_dims=None,
                                                     B=self.B)

        sx, sy = self.grid_res
        H, W = self.img_res
        gx, gy = tf.math.ceil(W/sx), tf.math.ceil(H/sy)
        nx, ny = tf.cast(gx+3, tf.int32), tf.cast(gy+3, tf.int32)

        self.transformer_regressor = TransformationRegressor(theta_units=2*ny*nx, input_dim=input_dim)


    def call(self, inputs):
        xs = self.loc_net(inputs)
        xs = self.flatten(xs)
        xs = Dropout(rate=self.drate)(xs)
        theta = self.transformer_regressor(xs)
        xt = self.transformer(inputs, theta, self.B)
        return xt


    def transform(self, inputs):
        # inputs = inputs.astype("float32")
        inputs = tf.cast(inputs, "float32")
        xs = self.loc_net(inputs)
        xs = self.flatten(xs)
        theta = self.transformer_regressor(xs)
        xt = self.transformer(inputs, theta, self.B)
        return xt


class BSplineRegistration(tf.keras.models.Model):

    def __init__(self, img_res, factor=1):
        super(BSplineRegistration, self).__init__()
        self.B = 1
        self.img_res = img_res
        self.loc_net = LocNet()

        _test_arr = np.ones((1, img_res[0], img_res[1], 1)).astype(np.float32)
        _test_arr = self.loc_net(_test_arr)
        self.grid_res = _test_arr.numpy().squeeze().shape
        self.grid_res = [self.grid_res[0], self.grid_res[1]]
        print("Grid res:", self.grid_res)

        self.transformer_regressor = TransformationRegressor(theta_units=self.grid_res[0] * self.grid_res[1] * 2,
                                                             input_dim=factor)
        self.grid_res = [self.grid_res[0] * np.sqrt(factor).astype(np.int32),
                         self.grid_res[1] * np.sqrt(factor).astype(np.int32)]
        self.transformer = SpatialTransformerBspline(img_res=img_res,
                                                     grid_res=self.grid_res,
                                                     out_dims=img_res,
                                                     B=self.B)

    def call(self, moving):
        xs = moving
        xs = self.loc_net(xs)
        xs = tf.transpose(xs, [0, 3, 1, 2])
        theta = self.transformer_regressor(xs)
        theta = tf.reshape(theta, (self.B, 2, self.grid_res[0], self.grid_res[1]))
        xt = self.transformer(moving, theta, self.B)
        return xt, theta


