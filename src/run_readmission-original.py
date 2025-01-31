# coding=utf-8
# Copyright 2018 The Google AI Language Team Authors and The HugginFace Inc. team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""BERT finetuning runner."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import csv
import os
import logging
import argparse
import random
import pandas as pd
import numpy as np
from tqdm import trange, tqdm
from datetime import datetime

import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt

# from scipy import interp

import wandb
import torch
from torch import nn
from torch.utils.data import TensorDataset, DataLoader, RandomSampler, SequentialSampler
from torch.utils.data.distributed import DistributedSampler
from pytorch_pretrained_bert.tokenization import BertTokenizer
from pytorch_pretrained_bert.optimization import BertAdam
from ranger21 import Ranger21 as RangerOptimizer
#important

from modeling_readmission import BertForSequenceClassification, BertForSequenceClassificationOriginal
from data_processor import convert_examples_to_features, readmissionProcessor
from evaluation import vote_score, vote_pr_curve

def copy_optimizer_params_to_model(named_params_model, named_params_optimizer):
    """ Utility function for optimize_on_cpu and 16-bits training.
        Copy the parameters optimized on CPU/RAM back to the model on GPU
    """
    for (name_opti, param_opti), (name_model, param_model) in zip(named_params_optimizer, named_params_model):
        if name_opti != name_model:
            logger.error("name_opti != name_model: {} {}".format(name_opti, name_model))
            raise ValueError
        param_model.data.copy_(param_opti.data)

def set_optimizer_params_grad(named_params_optimizer, named_params_model, test_nan=False):
    """ Utility function for optimize_on_cpu and 16-bits training.
        Copy the gradient of the GPU parameters to the CPU/RAMM copy of the model
    """
    is_nan = False
    for (name_opti, param_opti), (name_model, param_model) in zip(named_params_optimizer, named_params_model):
        if name_opti != name_model:
            logger.error("name_opti != name_model: {} {}".format(name_opti, name_model))
            raise ValueError
        if param_model.grad is not None:
            if test_nan and torch.isnan(param_model.grad).sum() > 0:
                is_nan = True
            if param_opti.grad is None:
                param_opti.grad = torch.nn.Parameter(param_opti.data.new().resize_(*param_opti.data.size()))
            param_opti.grad.data.copy_(param_model.grad.data)
        else:
            param_opti.grad = None
    return is_nan


def main():
    parser = argparse.ArgumentParser()

    ## Required parameters
    parser.add_argument("--data_dir",
                        default=None,
                        type=str,
                        required=True,
                        help="The input data dir. Should contain the .tsv files (or other data files) for the task.")
    parser.add_argument("--bert_model", default=None, type=str, required=True,
                        help="Bert pre-trained model selected in the list: bert-base-uncased, "
                             "bert-large-uncased, bert-base-cased, bert-base-multilingual, bert-base-chinese.")
    
    parser.add_argument("--readmission_mode", default = None, type=str, help="early notes or discharge summary")
    
    parser.add_argument("--task_name",
                        default=None,
                        type=str,
                        required=True,
                        help="The name of the task to train.")
    parser.add_argument("--output_dir",
                        default=None,
                        type=str,
                        required=True,
                        help="The output directory where the model checkpoints will be written.")

    ## Other parameters
    parser.add_argument("--max_seq_length",
                        default=128,
                        type=int,
                        help="The maximum total input sequence length after WordPiece tokenization. \n"
                             "Sequences longer than this will be truncated, and sequences shorter \n"
                             "than this will be padded.")
    parser.add_argument("--do_train",
                        default=False,
                        action='store_true',
                        help="Whether to run training.")
    parser.add_argument("--do_eval",
                        default=False,
                        action='store_true',
                        help="Whether to run eval on the dev set.")
    parser.add_argument("--train_batch_size",
                        default=32,
                        type=int,
                        help="Total batch size for training.")
    parser.add_argument("--eval_batch_size",
                        default=2,
                        type=int,
                        help="Total batch size for eval.")
    parser.add_argument("--learning_rate",
                        default=5e-5,
                        type=float,
                        help="The initial learning rate for Adam.")
    parser.add_argument("--num_train_epochs",
                        default=3.0,
                        type=float,
                        help="Total number of training epochs to perform.")
    # parser.add_argument("--warmup_proportion",
    #                     default=0.1,
    #                     type=float,
    #                     help="Proportion of training to perform linear learning rate warmup for. "
    #                          "E.g., 0.1 = 10%% of training.")
    parser.add_argument("--no_cuda",
                        default=False,
                        action='store_true',
                        help="Whether not to use CUDA when available")
    parser.add_argument("--local_rank",
                        type=int,
                        default=-1,
                        help="local_rank for distributed training on gpus")
    parser.add_argument('--seed', 
                        type=int, 
                        default=42,
                        help="random seed for initialization")
    parser.add_argument('--gradient_accumulation_steps',
                        type=int,
                        default=1,
                        help="Number of updates steps to accumulate before performing a backward/update pass.")                       
    parser.add_argument('--optimize_on_cpu',
                        default=False,
                        action='store_true',
                        help="Whether to perform optimization and keep the optimizer averages on CPU")
    parser.add_argument('--fp16',
                        default=False,
                        action='store_true',
                        help="Whether to use 16-bit float precision instead of 32-bit")
    parser.add_argument('--loss_scale',
                        type=float, default=128,
                        help='Loss scaling, positive power of 2 values can improve fp16 convergence.')
    parser.add_argument('-feat','--additional_features',
                        default=None,
                        nargs="*",
                        type=str,
                        choices=["admittime", "daystonextadmit", "duration", "diag_icd9", "diag_ccs", "proc_icd9", "proc_ccs", "ndc"],
                        help='Additional features to use as model input. Please select one or more of the following inputs: [admittime, daystonextadmit, duration, diag_icd9, diag_ccs, proc_icd9, proc_ccs, ndc]')
    parser.add_argument('--icd9_ccs_maxlength',
                        type=int,
                        default=40,
                        help="max length for icd9 and ccs tensors")
    parser.add_argument('--ndc_maxlength',
                        type=int,
                        default=200,
                        help="max length for ndc tensors")
    parser.add_argument('--freeze_bert',
                        default=False,
                        action='store_true',
                        help="Whether to freeze parameters from BERT layers or not. When frozen, these are not updated during model training.")

    args = parser.parse_args()
    
    logging.basicConfig(format = '%(asctime)s - %(levelname)s - %(name)s -   %(message)s', 
                    datefmt = '%m/%d/%Y %H:%M:%S',
                    level = logging.INFO)
    logger = logging.getLogger(__name__)
    
    current_time = datetime.now().strftime("%Y-%m-%d_%H:%M:%S_")

    ##Initialize wandb to upload run data
    wandb.init(project="clinicalBERT")#,config={"epochs": 4})
    run_name = wandb.run.name
    
    config = wandb.config
    # wandb.config.update({"lr": 0.1, "channels": 16})
    # config.learning_rate = 0.01
    
    processors = {
        "readmission": readmissionProcessor
    }

    maxLenDict={"icd9_ccs_maxlen": args.icd9_ccs_maxlength, "ndc_maxlen": args.ndc_maxlength}

    if args.local_rank == -1 or args.no_cuda:
        device = torch.device("cuda" if torch.cuda.is_available() and not args.no_cuda else "cpu")
        n_gpu = torch.cuda.device_count()
    else:
        device = torch.device("cuda", args.local_rank)
        n_gpu = 1
        # Initializes the distributed backend which will take care of sychronizing nodes/GPUs
        torch.distributed.init_process_group(backend='nccl')
        if args.fp16:
            logger.info("16-bits training currently not supported in distributed training")
            args.fp16 = False # (see https://github.com/pytorch/pytorch/pull/13496)
    logger.info("device %s n_gpu %d distributed training %r", device, n_gpu, bool(args.local_rank != -1))

    if args.gradient_accumulation_steps < 1:
        raise ValueError("Invalid gradient_accumulation_steps parameter: {}, should be >= 1".format(
                            args.gradient_accumulation_steps))

    args.train_batch_size = int(args.train_batch_size / args.gradient_accumulation_steps)

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if n_gpu > 0:
        torch.cuda.manual_seed_all(args.seed)

    if not args.do_train and not args.do_eval:
        raise ValueError("At least one of `do_train` or `do_eval` must be True.")

    args.output_dir = os.path.join(args.output_dir,current_time+run_name)

    if os.path.exists(args.output_dir) and os.listdir(args.output_dir):
        raise ValueError("Output directory ({}) already exists and is not empty.".format(args.output_dir))
    os.makedirs(args.output_dir, exist_ok=True)

    task_name = args.task_name.lower()

    if task_name not in processors:
        raise ValueError("Task not found: %s" % (task_name))

    processor = processors[task_name]()
    label_list = processor.get_labels()

    tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')

    model = BertForSequenceClassification.from_pretrained(args.bert_model, 1, args.additional_features)
    # model = BertForSequenceClassificationOriginal.from_pretrained(args.bert_model, 1)
    
    ## Setting WandBI to log gradients and model parameters
    wandb.watch(model)

    # print(list(model.named_parameters()))
# SEE THIS AND CHANGE MODEL NAMED PARAMETERS TO SEE WHAT PARAMETERS ARE APPEARING, WITHOUT THE GIANT TENSORS IN THE OUTPUT
    if args.fp16:
        model.half()
    model.to(device)
    if args.local_rank != -1:
        model = torch.nn.parallel.DistributedDataParallel(model, device_ids=[args.local_rank],
                                                          output_device=args.local_rank)
    elif n_gpu > 1:
        model = torch.nn.DataParallel(model)

    global_step = 0
    train_loss=100000
    number_training_steps=1
    global_step_check=0
    train_loss_history=[]
        
    if args.do_train:

        #if freeze_bert:
        for name, param in model.named_parameters():
            if name.startswith("bert"):
                param.requires_grad = False

        # Prepare optimizer
        if args.fp16:
            param_optimizer = [(n, param.clone().detach().to('cpu').float().requires_grad_()) \
                                for n, param in model.named_parameters()]
        elif args.optimize_on_cpu:
            param_optimizer = [(n, param.clone().detach().to('cpu').requires_grad_()) \
                                for n, param in model.named_parameters()]
        else:
            param_optimizer = list(model.named_parameters())
        no_decay = ['bias', 'gamma', 'beta']
        optimizer_grouped_parameters = [
            {'params': [p for n, p in param_optimizer if not any(nd in n for nd in no_decay)], 'weight_decay_rate': 0.01},
            {'params': [p for n, p in param_optimizer if any(nd in n for nd in no_decay)], 'weight_decay_rate': 0.0}
            ]
        # optimizer = BertAdam(optimizer_grouped_parameters,
        #                      lr=args.learning_rate,
        #                      warmup=args.warmup_proportion,
        #                      t_total=num_train_steps)
        
        train_examples = processor.get_train_examples(args.data_dir, args.additional_features)
        num_train_steps = int(len(train_examples) / args.train_batch_size / args.gradient_accumulation_steps * args.num_train_epochs)
        
        train_features = convert_examples_to_features(
            train_examples, label_list, args.max_seq_length, tokenizer, args.additional_features, maxLenDict)
        logger.info("***** Running training *****")
        logger.info("  Num examples = %d", len(train_examples))
        logger.info("  Batch size = %d", args.train_batch_size)
        logger.info("  Num steps = %d", num_train_steps)
        all_input_ids   = torch.tensor([f.input_ids for f in train_features], dtype=torch.long)
        all_input_mask  = torch.tensor([f.input_mask for f in train_features], dtype=torch.long)
        all_segment_ids = torch.tensor([f.segment_ids for f in train_features], dtype=torch.long)
        all_label_ids   = torch.tensor([f.label_id for f in train_features], dtype=torch.long)
        tensors = [all_input_ids, all_input_mask, all_segment_ids, all_label_ids]

        featurePositionDict = {}
        positionIdx=0
        # additionalFeatureOrder = [feature for feature in args.additional_features]
        if args.additional_features is not None:
            if "admittime" in args.additional_features:
                tensors.append(torch.tensor([f.admittime for f in train_features], dtype=torch.long))
                featurePositionDict["admittime"] = positionIdx
                positionIdx+=1
            if "daystonextadmit" in args.additional_features:
                tensors.append(torch.tensor([f.daystonextadmit for f in train_features], dtype=torch.long))
                featurePositionDict["daystonextadmit"] = positionIdx
                positionIdx+=1
            if "duration"  in args.additional_features:
                tensors.append(torch.tensor([f.duration for f in train_features], dtype=torch.long))
                featurePositionDict["duration"] = positionIdx
                positionIdx+=1
            if "diag_icd9" in args.additional_features:
                tensors.append(torch.tensor([f.diag_icd9 for f in train_features], dtype=torch.long))
                featurePositionDict["diag_icd9"] = positionIdx
                positionIdx+=1
            if "diag_ccs"  in args.additional_features:
                tensors.append(torch.tensor([f.diag_ccs for f in train_features], dtype=torch.long))
                featurePositionDict["diag_ccs"] = positionIdx
                positionIdx+=1
            if "proc_icd9" in args.additional_features:
                tensors.append(torch.tensor([f.proc_icd9 for f in train_features], dtype=torch.long))
                featurePositionDict["proc_icd9"] = positionIdx
                positionIdx+=1
            if "proc_ccs"  in args.additional_features:
                tensors.append(torch.tensor([f.proc_ccs for f in train_features], dtype=torch.long))
                featurePositionDict["proc_ccs"] = positionIdx
                positionIdx+=1
            if "ndc"       in args.additional_features:
                tensors.append(torch.tensor([f.ndc for f in train_features], dtype=torch.long))
                featurePositionDict["ndc"] = positionIdx
                positionIdx+=1

        train_data = TensorDataset(*tensors)

        if args.local_rank == -1:
            train_sampler = RandomSampler(train_data)
        else:
            train_sampler = DistributedSampler(train_data)
        train_dataloader = DataLoader(train_data, sampler=train_sampler, batch_size=args.train_batch_size)
        
        optimizer = RangerOptimizer(params=optimizer_grouped_parameters,
                                    lr=args.learning_rate,
                                    # warmup_pct_default=args.warmup_proportion,
                                    num_epochs=args.num_train_epochs,
                                    num_batches_per_epoch=len(train_dataloader)
                                   )
                                           
        model.train()
        for epo in trange(int(args.num_train_epochs), desc="Epoch"):
            tr_loss = 0
            nb_tr_examples, nb_tr_steps = 0, 0
            for step, batch in enumerate(tqdm(train_dataloader)):
                # batch = tuple(t.to(device) for t in batch)
                #
                input_ids, input_mask, segment_ids, label_ids, *extraFeatures = batch
                input_ids = input_ids.to(device)
                input_mask = input_mask.to(device)
                segment_ids = segment_ids.to(device)
                label_ids = label_ids.to(device)
                if extraFeatures:
                    extraFeatures = [feature.to(device) for feature in extraFeatures]
                    loss, logits = model(input_ids, segment_ids, input_mask, label_ids, additional_features_name=args.additional_features, additional_features_tensors=extraFeatures, feature_position_dict=featurePositionDict)
                else:
                    loss, logits = model(input_ids, segment_ids, input_mask, label_ids)

                if n_gpu > 1:
                    loss = loss.mean() # mean() to average on multi-gpu.
                if args.fp16 and args.loss_scale != 1.0:
                    # rescale loss for fp16 training
                    # see https://docs.nvidia.com/deeplearning/sdk/mixed-precision-training/index.html
                    loss = loss * args.loss_scale
                if args.gradient_accumulation_steps > 1:
                    loss = loss / args.gradient_accumulation_steps
                loss.backward()
                train_loss_history.append(loss.item())
                tr_loss += loss.item()
                nb_tr_examples += input_ids.size(0)
                nb_tr_steps += 1
                if (step + 1) % args.gradient_accumulation_steps == 0:
                    if args.fp16 or args.optimize_on_cpu:
                        if args.fp16 and args.loss_scale != 1.0:
                            # scale down gradients for fp16 training
                            for param in model.parameters():
                                if param.grad is not None:
                                    param.grad.data = param.grad.data / args.loss_scale
                        is_nan = set_optimizer_params_grad(param_optimizer, model.named_parameters(), test_nan=True)
                        if is_nan:
                            logger.info("FP16 TRAINING: Nan in gradients, reducing loss scaling")
                            args.loss_scale = args.loss_scale / 2
                            model.zero_grad()
                            continue
                        optimizer.step()
                        copy_optimizer_params_to_model(model.named_parameters(), param_optimizer)
                    else:
                        optimizer.step()
                    model.zero_grad()
                    global_step += 1
                
                # if (step+1) % 200 == 0:
                #     string = 'step '+str(step+1)
                #     print (string)

            
            
            train_loss=tr_loss
            global_step_check=global_step
            number_training_steps=nb_tr_steps
            wandb.log({"Training loss": train_loss/number_training_steps})
            
        string = os.path.join(args.output_dir, 'pytorch_model_new_'+args.readmission_mode+'.bin')
        torch.save(model.state_dict(), string)

        fig1 = plt.figure()
        plt.plot(train_loss_history)
        fig_name = os.path.join(args.output_dir, 'loss_history.png')
        fig1.savefig(fig_name, dpi=fig1.dpi)
    
    m = nn.Sigmoid()
    if args.do_eval:
        eval_examples = processor.get_test_examples(args.data_dir, args.additional_features)
        eval_features = convert_examples_to_features(
            eval_examples, label_list, args.max_seq_length, tokenizer, args.additional_features, maxLenDict)
        logger.info("***** Running evaluation *****")
        logger.info("  Num examples = %d", len(eval_examples))
        logger.info("  Batch size = %d", args.eval_batch_size)
        all_input_ids = torch.tensor([f.input_ids for f in eval_features], dtype=torch.long)
        all_input_mask = torch.tensor([f.input_mask for f in eval_features], dtype=torch.long)
        all_segment_ids = torch.tensor([f.segment_ids for f in eval_features], dtype=torch.long)
        all_label_ids = torch.tensor([f.label_id for f in eval_features], dtype=torch.long)
        tensors = [all_input_ids, all_input_mask, all_segment_ids, all_label_ids]

        featurePositionDict = {}
        positionIdx=0
        # additionalFeatureOrder = [feature for feature in args.additional_features]
        
        if args.additional_features is not None:
            if "admittime" in args.additional_features:
                tensors.append(torch.tensor([f.admittime for f in eval_features], dtype=torch.long))
                featurePositionDict["admittime"] = positionIdx
                positionIdx+=1
            if "daystonextadmit" in args.additional_features:
                tensors.append(torch.tensor([f.daystonextadmit for f in eval_features], dtype=torch.long))
                featurePositionDict["daystonextadmit"] = positionIdx
                positionIdx+=1
            if "duration"  in args.additional_features:
                tensors.append(torch.tensor([f.duration for f in eval_features], dtype=torch.long))
                featurePositionDict["duration"] = positionIdx
                positionIdx+=1
            if "diag_icd9" in args.additional_features:
                tensors.append(torch.tensor([f.diag_icd9 for f in eval_features], dtype=torch.long))
                featurePositionDict["diag_icd9"] = positionIdx
                positionIdx+=1
            if "diag_ccs"  in args.additional_features:
                tensors.append(torch.tensor([f.diag_ccs for f in eval_features], dtype=torch.long))
                featurePositionDict["diag_ccs"] = positionIdx
                positionIdx+=1
            if "proc_icd9" in args.additional_features:
                tensors.append(torch.tensor([f.proc_icd9 for f in eval_features], dtype=torch.long))
                featurePositionDict["proc_icd9"] = positionIdx
                positionIdx+=1
            if "proc_ccs"  in args.additional_features:
                tensors.append(torch.tensor([f.proc_ccs for f in eval_features], dtype=torch.long))
                featurePositionDict["proc_ccs"] = positionIdx
                positionIdx+=1
            if "ndc"       in args.additional_features:
                tensors.append(torch.tensor([f.ndc for f in eval_features], dtype=torch.long))
                featurePositionDict["ndc"] = positionIdx
                positionIdx+=1

        eval_data = TensorDataset(*tensors)

        if args.local_rank == -1:
            eval_sampler = SequentialSampler(eval_data)
        else:
            eval_sampler = DistributedSampler(eval_data)
        eval_dataloader = DataLoader(eval_data, sampler=eval_sampler, batch_size=args.eval_batch_size)
        model.eval()
        eval_loss, eval_accuracy = 0, 0
        nb_eval_steps, nb_eval_examples = 0, 0
        true_labels=[]
        pred_labels=[]
        logits_history=[]

        for input_ids, input_mask, segment_ids, label_ids, *extraFeatures in tqdm(eval_dataloader):
            input_ids = input_ids.to(device)
            input_mask = input_mask.to(device)
            segment_ids = segment_ids.to(device)
            label_ids = label_ids.to(device)

            with torch.no_grad():
                if extraFeatures:
                    extraFeatures = [feature.to(device) for feature in extraFeatures]
                    tmp_eval_loss, temp_logits = model(input_ids, segment_ids, input_mask, label_ids, additional_features_name=args.additional_features, additional_features_tensors=extraFeatures, feature_position_dict=featurePositionDict)
                    logits = model(input_ids,segment_ids,input_mask, additional_features_name=args.additional_features, additional_features_tensors=extraFeatures, feature_position_dict=featurePositionDict)
                else:
                    tmp_eval_loss, temp_logits = model(input_ids, segment_ids, input_mask, label_ids)
                    logits = model(input_ids, segment_ids, input_mask)
            
            logits = torch.squeeze(m(logits)).detach().cpu().numpy()
            label_ids = label_ids.to('cpu').numpy()

            outputs = np.asarray([1 if i else 0 for i in (logits.flatten()>=0.5)])
            tmp_eval_accuracy=np.sum(outputs == label_ids)
            
            true_labels = true_labels + label_ids.flatten().tolist()
            pred_labels = pred_labels + outputs.flatten().tolist()
            logits_history = logits_history + logits.flatten().tolist()
       
            eval_loss += tmp_eval_loss.mean().item()
            eval_accuracy += tmp_eval_accuracy

            nb_eval_examples += input_ids.size(0)
            nb_eval_steps += 1
            
        eval_loss = eval_loss / nb_eval_steps
        eval_accuracy = eval_accuracy / nb_eval_examples
        df = pd.DataFrame({'logits':logits_history, 'pred_label': pred_labels, 'label':true_labels})
        
        wandb.log({"Test loss": eval_loss, "Test accuracy": eval_accuracy})        
        
        string = 'logits_clinicalbert_'+args.readmission_mode+'_chunks.csv'
        df.to_csv(os.path.join(args.output_dir, string))
        
        df_test = pd.read_csv(os.path.join(args.data_dir, "test.csv"))

        fpr, tpr, df_out = vote_score(df_test, logits_history, args)
        
        string = 'logits_clinicalbert_'+args.readmission_mode+'_readmissions.csv'
        df_out.to_csv(os.path.join(args.output_dir,string))
        
        rp80 = vote_pr_curve(df_test, logits_history, args)
        
        result = {'eval_loss': eval_loss,
                  'eval_accuracy': eval_accuracy,                 
                  'global_step': global_step_check,
                  'training loss': train_loss/number_training_steps,
                  'RP80': rp80}
        
        output_eval_file = os.path.join(args.output_dir, "eval_results.txt")
        with open(output_eval_file, "w") as writer:
            logger.info("***** Eval results *****")
            for key in sorted(result.keys()):
                logger.info("  %s = %s", key, str(result[key]))
                writer.write("%s = %s\n" % (key, str(result[key])))
    
    ##Close the run by finishing it
    wandb.finish()
        
if __name__ == "__main__":
    main()
