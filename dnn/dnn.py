#!/usr/bin/env python3
'''
    File name: dnn.py
    Author: Maxime Bergeron
    Date last modified: 30/04/2019
    Python Version: 3.5

    A python Tensorflow handler
'''
import sys, os, shutil
import argparse
import csv
import tensorflow as tf
import tensorboard
import logging
import datetime
import glob
from argparse import RawTextHelpFormatter
from collections import Counter

#######################
# CLASSES & FUNCTIONS #
#######################

runOnce = False

def _roomClassifier(features, labels, mode, params):
    if mode == tf.estimator.ModeKeys.PREDICT:
        tf.logging.info("roomclassifier: PREDICT, {}".format(mode))
    elif mode == tf.estimator.ModeKeys.EVAL:
        tf.logging.info("roomclassifier: EVAL, {}".format(mode))
    elif mode == tf.estimator.ModeKeys.TRAIN:
        tf.logging.info("roomclassifier: TRAIN, {}".format(mode))

    net = tf.feature_column.input_layer(features, params["feature_columns"])
    for units in params['hidden_units']:
        net = tf.layers.dense(net, units=units, activation=tf.nn.relu)

    logits = tf.layers.dense(net, params['n_classes'], activation=None)
    predicted_classes = tf.argmax(logits, 1)
    if mode == tf.estimator.ModeKeys.PREDICT:
        predictions = {
            'class_ids': predicted_classes[:, tf.newaxis],
            'probabilities': tf.nn.softmax(logits),
            'logits': logits,
        }
        return tf.estimator.EstimatorSpec(mode, predictions=predictions)

    loss = tf.losses.sparse_softmax_cross_entropy(labels=labels, logits=logits)
    accuracy = tf.metrics.accuracy(labels, predictions=predicted_classes)
    metrics = {'average_accuracy': accuracy}
    tf.summary.scalar('accuracy', accuracy[1])
    tf.summary.scalar('loss', loss)

    if mode == tf.estimator.ModeKeys.EVAL:
        return tf.estimator.EstimatorSpec(mode, loss=loss, eval_metric_ops=metrics)

    assert mode == tf.estimator.ModeKeys.TRAIN, "TRAIN is only ModeKey left"

    optimizer = tf.train.AdamOptimizer(0.05, beta1=0.9, beta2=0.999, epsilon=1e-08)
    #optimizer = tf.train.AdagradOptimizer(0.001)

    train_op = optimizer.minimize(loss, global_step=tf.train.get_global_step())

    return tf.estimator.EstimatorSpec(mode, loss=loss, train_op=train_op)

def _input_csv(file_path, feature_names, is_prediction = False, is_evaluation = False):
    def decode_csv(line):
        if (is_prediction):
            col1, col2, col3, col4, col5, col6 = tf.decode_csv(file_path, [[0.0], [0.0], [0.0], [0.0], [0.0], [0.0]], field_delim=',')
            features = [col1, col2, col3, col4, col5, col6]
            d = dict(zip(feature_names, features))
            return d
        else:
            col1, col2, col3, col4, col5, col6, col7 = tf.decode_csv(line, [[0], [0.0], [0.0], [0.0], [0.0], [0.0], [0.0]], field_delim=',')
            features = [col2, col3, col4, col5, col6, col7]
            d = dict(zip(feature_names, features)), col1
            return d

    if is_evaluation:
        dataset = (tf.data.TextLineDataset(file_path)
            .skip(0)
            .map(decode_csv, num_parallel_calls=2)
            .shuffle(1000)
            .batch(3)
        )
    elif is_prediction:
        dataset = (tf.data.Dataset.from_generator(lambda: file_path, tf.string)
            .map(decode_csv)
            .batch(1)
        )
        iterator = dataset.make_one_shot_iterator()
        batch_features = iterator.get_next()
        return batch_features
    else:
        dataset = (tf.data.TextLineDataset(file_path)
            .skip(0)
            .map(decode_csv, num_parallel_calls=2)
            .shuffle(1000)
            .repeat()
            .batch(3)
        )
    iterator = dataset.make_one_shot_iterator()
    batch_features, batch_labels = iterator.get_next()
    return batch_features, batch_labels

def _get_features():
    featureNames = ['r1_mean', 'r1_rssi', 'r2_mean', 'r2_rssi', 'r3_mean', 'r3_rssi']
    featureColumns = [tf.feature_column.numeric_column('r1_mean', dtype=tf.float64), tf.feature_column.numeric_column('r1_rssi', dtype=tf.float64), \
                      tf.feature_column.numeric_column('r2_mean', dtype=tf.float64), tf.feature_column.numeric_column('r2_rssi', dtype=tf.float64), \
                      tf.feature_column.numeric_column('r3_mean', dtype=tf.float64), tf.feature_column.numeric_column('r3_rssi', dtype=tf.float64)]
    return featureNames,featureColumns

def run_tensorflow(CSVFile="train.log", TestBefore=False, HasRestart=False, LaunchTboard=False, TfTrain=False, TfTest=False, TfPredict=False, 
                   TfFolder="./tf", PredictList=None, Verbose=False, Logfile=False, _called=True):
    if Verbose:
        logging.getLogger().setLevel(logging.INFO)

    if (not CSVFile and not LaunchTboard):
        print("[FATAL] A valid filename is required")
        quit()

    if (TfPredict and (TfTest or TfTrain)):
        print("[FATAL] Do not run a prediction on the same run as a training or testing. Quitting.")
        quit()

    if (not TfPredict and PredictList):
        print("[FATAL] You need to set the algorithm to --predict with a line prediction. Quitting.")
        quit()      

    if (HasRestart):
        try:
            shutil.rmtree(TfFolder)
        except (FileNotFoundError):
            pass

    feature_names,feature_columns = _get_features()

    print("Creating rooms list...")
    lines_room = []
    roomCount = 0

    if _called:
        CSVFile = "./dnn/" + CSVFile
        TrainRooms = "./dnn/train-rooms.log"
        TrainClean = "./dnn/train-clean.log"
    else:
        CSVFile = "./" + CSVFile
        TrainRooms = "./train-rooms.log"
        TrainClean = "./train-clean.log"

    with open(CSVFile, "r") as _f:
        with open(TrainRooms, "w") as _w:
            with open(TrainClean, "w") as _w2:
                _fcsv = csv.reader(_f,delimiter=',')
                for row in _fcsv:
                    if (row[0] not in lines_room):
                        _w.write("{},{}\n".format(row[0],roomCount))
                        lines_room.append(row[0])
                        roomCount = roomCount + 1
                    _w2.write("{},{},{},{},{},{},{}\n".format(lines_room.index(row[0]), row[1], row[2], row[3], row[4], row[5], row[6]))

    if (TestBefore):
        if (TfPredict):
            next_batch = _input_csv(TrainClean, feature_names, True)
        else:
            next_batch = _input_csv(TrainClean, feature_names)

        with tf.Session() as sess:
            first_batch = sess.run(next_batch)
        print(first_batch)

    TfConfig = tf.estimator.RunConfig(session_config=tf.ConfigProto(
        inter_op_parallelism_threads=1,
        intra_op_parallelism_threads=1,
        operation_timeout_in_ms=20000
        ), model_dir=TfFolder)

    N_CLASSES = roomCount

    '''
    if (not HasRestart):
        classifier = tf.estimator.Estimator(
            model_fn=_roomClassifier,
            config=TfConfig,
            params={
                "feature_columns":feature_columns,
                "hidden_units":[3,3,2],
                "n_classes":N_CLASSES,
                "config":TfConfig
            },
            warm_start_from=TfFolder)
    else:
        classifier = tf.estimator.Estimator(
            model_fn=_roomClassifier,
            config=TfConfig,
            params={
                "feature_columns":feature_columns,
                "hidden_units":[3,3,2],
                "n_classes":N_CLASSES,
                "config":TfConfig
            })
    '''

    classifier = tf.estimator.DNNClassifier(
         feature_columns=feature_columns,
         hidden_units=[3, 3, 2],
         optimizer=tf.train.AdamOptimizer(1e-4),
         n_classes=N_CLASSES,
         #dropout=0.1,
         model_dir='./tf'
        )

    '''
    classifier = tf.estimator.LinearClassifier(feature_columns,
                                    n_classes=N_CLASSES)
    '''

    if (TfTrain):
        if (not Verbose):
            print("Running TENSORFLOW training, please wait...")
        classifier.train(input_fn=lambda: _input_csv(TrainClean, feature_names), steps=100000)

    CSVTestFile = "./train-clean.log"
    if (TfTest):
        if (not Verbose):
            print("Running TENSORFLOW testing, please wait...")
        accuracy_score = classifier.evaluate(input_fn=lambda: _input_csv(CSVTestFile, feature_names, is_evaluation=True))["accuracy"]
        print("\nTest Accuracy: {0:f}%\n".format(accuracy_score*100))

    if (TfPredict):
        if (not Verbose and PredictList is None):
            print("Running TENSORFLOW predictions, please wait...")
        if (PredictList):
            predict_results = classifier.predict(input_fn=lambda: _input_csv(PredictList, feature_names, is_prediction=True))
            for prediction in predict_results:
                with open(TrainRooms, 'r') as _trcsv:
                    _fcsv = csv.reader(_trcsv,delimiter=',')
                    for row in _fcsv:
                        if int(row[1]) == int(prediction["class_ids"][0]):
                            print(row[0])
                            return row[0]
        else:
            print("You need to send a data request via the system args with --predict-line. Quitting.")
            quit()

    if (LaunchTboard):
        print("Launching tensorboard...")
        os.system('python3 -m tensorboard.main --logdir={0}'.format(TfFolder))

    quit()


#######################
#######################
#######################
 
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Machine learning - TensorFlow algorithms', formatter_class=RawTextHelpFormatter)
    parser.add_argument('dbfile', metavar='CSV_Filename', nargs='?', type=str, default=sys.stdin, help='CSV file of the trimmed and cleaned patient database')
    # Training ops
    parser.add_argument('--train', action='store_true', default=False, help='Run the training algorithm. If set to false will use stored model (default = False)')
    parser.add_argument('--test', action='store_true', default=False, help='Run the testing algorithm with a random subset of input data (default = False)')
    parser.add_argument('--sanity-check', action='store_true', default=False, help='Check input from DB before analyzing (default = False)')
    # Prediction ops
    parser.add_argument('--predict', action='store_true', default=False, help='Run the prediction algorithm on a tensorflowpred CSV database (default = False)')
    parser.add_argument('--predict-line', metavar='CSV_line', default=None, type=str, help='Run the prediction algorithm on a single CSV line (default = None)')    
    # Optional ops and tweakables
    parser.add_argument('--restart', action='store_true', default=False, help='Purge local tensorflow data and restart with new analysis (default = False)')
    parser.add_argument('--board', action='store_true', default=False, help='Get detailed results at the end of the analysis (default = False)')
    parser.add_argument('--model-dir', metavar='Directory', type=str, default="./tf", nargs="?", help='Directory to stock the model files - new folders require the --restart op (Default = ./tf)')
    parser.add_argument('--verbose', action='store_true', default=False, help='Print debug INFO to the console (default = False)')
    parser.add_argument('--logfile', action='store_true', default=False, help='Log the output results to file (in the logs folder)')

    args = parser.parse_args()
    run_tensorflow(args.dbfile, args.sanity_check, args.restart, args.board, args.train, args.test, args.predict, args.model_dir, 
        args.predict_line, args.verbose, args.logfile, _called=False)