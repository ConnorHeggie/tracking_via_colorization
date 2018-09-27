from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf

from .resnet import ResNet


class ResNetColorizer(ResNet):
    def __init__(self, is_training=True, data_format='channels_last', batch_norm_decay=0.997, batch_norm_epsilon=1e-5):
        super(ResNetColorizer, self).__init__(is_training, data_format, batch_norm_decay, batch_norm_epsilon)

    def forward(self, images, labels, temperature=1.0, num_labels=16, input_data_format='channels_last'):
        # images [BATCH, 4, HEIGHT(256), WIDTH(256), CHANNEL(1)]
        # labels [BATCH, 4, HEIGHT(32), WIDTH(32), CHANNEL(1)]
        # features [BATCH * 4, HEIGHT(32), WIDTH(32), CHANNEL(64)]
        features = self.feature(tf.reshape(images, (-1, 256, 256, 1)), input_data_format)
        _, height, width, channels = features.shape.as_list()
        area = height * width

        features = tf.reshape(features, (-1, 4, height, width, channels))
        splited_features = tf.split(features, num_or_size_splits=4, axis=1)
        splited_labels = tf.split(labels, num_or_size_splits=4, axis=1)

        reference_features = tf.stack(splited_features[:3], axis=1)
        reference_labels = tf.stack(splited_labels[:3], axis=1)
        target_features = tf.stack(splited_features[3:], axis=1)
        target_labels = tf.stack(splited_labels[3:], axis=1)

        with tf.name_scope('similarity_matrix') as name_scope:
            ref = tf.transpose(tf.reshape(reference_features, [-1, area * 3, channels]), perm=[0, 2, 1])
            tar = tf.reshape(target_features, [-1, area, channels])
            tf.logging.info('similarity innerproduct %s x %s', tar.get_shape(), ref.get_shape())

            innerproduct = tf.matmul(tar, ref)
            similarity_mat = tf.nn.softmax(innerproduct / temperature, 2)
            tf.logging.info('image after unit %s: %s', name_scope, similarity_mat.get_shape())

        with tf.name_scope('prediction') as name_scope:
            ref = tf.reshape(reference_labels, (-1, area * 3))
            tar = tf.reshape(target_labels, (-1, height, width, channels))
            dense_reference_labels = tf.one_hot(ref, num_labels)

            prediction = tf.matmul(similarity_mat, dense_reference_labels)
            prediction = tf.reshape(prediction, [-1, height, width, num_labels])
            target_labels = tf.reshape(target_labels, [-1, height, width, 1])
            tf.logging.info('image after unit %s: %s', name_scope, prediction.get_shape())
        return similarity_mat, prediction, tar


    def feature(self, x, input_data_format='channels_last'):
        # resnet_layer = self._residual_v2
        resnet_layer = self._bottleneck_residual_v2

        assert input_data_format in ('channels_first', 'channels_last')
        if self._data_format != input_data_format:
            if input_data_format == 'channels_last':
                x = tf.transpose(x, [0, 3, 1, 2])
            else:
                x = tf.transpose(x, [0, 2, 3, 1])

        with tf.name_scope('stage0') as name_scope:
            x = x / 128 - 1
            x = self._conv(x, kernel_size=3, filters=32, strides=1)
            x = self._batch_norm(x)
            x = self._relu(x)
            tf.logging.info('image after unit %s: %s', name_scope, x.get_shape())

        with tf.name_scope('stage1'):
            x = resnet_layer(x, kernel_size=3, in_filter=32, out_filter=64, stride=2)
            x = resnet_layer(x, kernel_size=3, in_filter=64, out_filter=64, stride=1)
            x = resnet_layer(x, kernel_size=3, in_filter=64, out_filter=64, stride=1)
            x = resnet_layer(x, kernel_size=3, in_filter=64, out_filter=64, stride=1)

        with tf.name_scope('stage2'):
            x = resnet_layer(x, kernel_size=3, in_filter=64, out_filter=128, stride=2)
            x = resnet_layer(x, kernel_size=3, in_filter=128, out_filter=128, stride=1)
            x = resnet_layer(x, kernel_size=3, in_filter=128, out_filter=128, stride=1)
            x = resnet_layer(x, kernel_size=3, in_filter=128, out_filter=128, stride=1)

        with tf.name_scope('stage3'):
            x = resnet_layer(x, kernel_size=3, in_filter=128, out_filter=256, stride=2)
            x = resnet_layer(x, kernel_size=3, in_filter=256, out_filter=256, stride=1)
            x = resnet_layer(x, kernel_size=3, in_filter=256, out_filter=256, stride=1)
            x = resnet_layer(x, kernel_size=3, in_filter=256, out_filter=256, stride=1)

        with tf.name_scope('stage4'):
            x = resnet_layer(x, kernel_size=3, in_filter=256, out_filter=256, stride=1)
            x = resnet_layer(x, kernel_size=3, in_filter=256, out_filter=256, stride=1)
            x = resnet_layer(x, kernel_size=3, in_filter=256, out_filter=256, stride=1)
            x = resnet_layer(x, kernel_size=3, in_filter=256, out_filter=256, stride=1)

        with tf.name_scope('feature'):
            x = resnet_layer(x, kernel_size=3, in_filter=256, out_filter=64, stride=1)

        return x