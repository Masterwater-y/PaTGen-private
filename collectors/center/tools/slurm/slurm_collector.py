import pandas as pd
import time
import os
import re


from collectors.center.tools.collector import Collector
from collectors.center.center_constants import *



class SlurmCollector(Collector):
    def __init__(self) -> None:
        super().__init__(
            name = "slurm_collctor",
            data_type = "aggregate",
            tool_layer = "server",
            avail_sets = {
                "job_basic":["jobid","jobname","priority","state"],
                "job_res":["cpu","mem","ntasks","nodes"],
                "job_time":["elapsedraw","submit","start","end","suspended"],
                "user_config":["nodes(req)","mem(req)","mem_per_cpu(req)","cpus_per_task(req)",\
                    "ntasks_per_node(req)","distribution(req)"]
            }
        )
        self.taskid_list = ["299", "300"]

    
    def start_collection(self, interval=1):
        cur_dir = os.path.abspath('.')
        os.chdir(os.path.split(os.path.realpath(__file__))[0])
        if not os.path.exists("data/pid"):
            os.system("mkdir -p data/pid")
            os.system("mkdir -p data/raw")
            os.system("mkdir -p data/parse")
        self.end_collection()
        os.chdir(cur_dir)
        
    
    def end_collection(self):
        cur_dir = os.path.abspath('.')
        os.chdir(os.path.split(os.path.realpath(__file__))[0])
        pid_list = os.listdir('./data/pid')
        for pid_file in pid_list:
            pid = open(f"./data/pid/{pid_file}").read()
            os.system(f'kill {pid}')
            os.remove(f"./data/pid/{pid_file}")
        os.chdir(cur_dir)
        
        
    def raw_data_proc(self, data_len=MAX_COLLECTED_TIME):
        cur_dir = os.path.abspath('.')
        os.chdir(os.path.split(os.path.realpath(__file__))[0]+"/data")
        os.system("rm -rf ./raw/*")
        os.system("rm -rf ./parse/*")
        self.data = pd.DataFrame()
        for taskID in self.taskid_list:
            self.__get_raw_data(taskID)
            raw_data_df = self.__parse_raw_data(taskID)
            script_data_df = self.__parse_script_file(taskID)
            task_df = pd.concat([raw_data_df, script_data_df], axis=1)
            task_df = task_df[[attr for subset in self.avail_sets.values() for attr in subset]]
            self.data = pd.concat([self.data, task_df])
        os.chdir(cur_dir)
    
    # parse the slurm scripts that user submitted
    def __parse_script_file(self, taskID):
        """
        Parse the slurm script and store configurations.

        ---
        Attention : Running path should be : ./data/

        ---
        Script file should be like:
          #!/bin/bash
          #SBATCH .. ...
        """
        result = pd.DataFrame(columns=self.avail_sets["user_config"])
        try:
            with open(f"./raw/script.{taskID}", "r+") as f:
                data = f.readlines()
                for lineno in range(3, len(data)):
                    if re.match(r"#SBATCH", data[lineno]):
                        varLine = re.split(r"\s|=", data[lineno])
                        varName = varLine[1].replace("-", " ").strip()
                        varValue = varLine[2]
                        if varName == "N" or varName == "nodes":
                            result.loc[0, "nodes(req)"] = varValue
                        elif varName == "cpus per task":
                            result.loc[0, "cpus_per_task(req)"] = varValue
                        elif varName == "ntasks per node":
                            result.loc[0, "ntasks_per_node(req)"] = varValue
                        elif varName == "mem per cpu":
                            result.loc[0, "mem_per_cpu(req)"] = varValue
                        elif varName == "mem":
                            result.loc[0, "mem(req)"] = varValue
                        elif varName == "m" or varName == "distribution":
                            result.loc[0, "distribution(req)"] = varValue
                        else:
                            pass
                    else:
                        break
                result = result.fillna("-1")
                return result
        # Skip if batch script is not recorded.
        except IOError:
            pass
    
    # parse the raw data from sacct command
    def __parse_raw_data(self, taskID):
        """
        Parse the accounting data.

        Jobstep is associated with a srun or mpirun, a single command won't appear in JobID.
         - JobID without a dot : shows the infomation for the whole job
         - JobID like A.batch : shows the information of the node that the script runs on 
         - JobID like A.B : shows the information of jobstep B in job A
        
        Different data has different source:
         - Get from the whole job : jobid, jobname, elpased, start, end, submit, priority
         - Get from line 6 : ntasks, alloctres
         - Analyzed from all lines: state
        
        ---
        Attention : This function should be called after the whole job is finished, or the infomation of jobstep would be incomplete.

        Attention : Running path should be : ./data/

        ---
        Raw data we get may be like:
        
          JobID                JobName ElapsedRaw    Start      End   Submit  Suspended      State   Priority   NTasks                      AllocTRES 
          186        test-tau-throttle        772 13:02:23 13:15:15 13:02:23   00:00:00  COMPLETED 4294901620          billing=12,cpu=12,mem=24G,nod+ 
          186.batch              batch        772 13:02:23 13:15:15 13:02:23   00:00:00  COMPLETED                   1            cpu=4,mem=8G,node=1 
          186.0               hostname          0 13:02:23 13:02:23 13:02:23   00:00:00  COMPLETED                   3          cpu=12,mem=24G,node=3 
          186.1        hydra_pmi_proxy        764 13:02:31 13:15:15 13:02:31   00:00:00  COMPLETED                   3          cpu=12,mem=24G,node=3
        """
        
        result = []
        attributes = ["jobid", "jobname", "elapsedraw", "start", "end", "submit", "suspended", "priority",\
            "cpu", "mem", "nodes", "ntasks", "state"]
        with open(f"./raw/sacct.{taskID}", "r+") as f:
            data = f.readlines()
            data = [re.split(r'\s+', line.strip()) for line in data]
            # Read line 3 and parse data
            wholeJobInfo = data[2]
            result += wholeJobInfo[:7]
            
            # Search for priority
            # Here may cause bugs because I recognize priority by its length, and I assume that priority should be a number more than 9999.
            for i in range(-1,-4,-1):
                if len(wholeJobInfo[i]) > 4 and wholeJobInfo[i].isdigit():
                    result.append(wholeJobInfo[i])
                    break
            
            # get resource allocation of the whole job
            if re.search("=", wholeJobInfo[-1]):
                allocRes = wholeJobInfo[-1].split(",")
                for res in allocRes:
                    resNV = res.split("=")
                    if resNV[0] != "billing":
                        result.append(resNV[1])
                        
            if len(result) == 8:
                result += ['-1', '-1', '-1']
            
            # We use the last jobstep to 
            jobState = "COMPLETED"
            for lineno in range(2,len(data)):
                # result of the job is defined by the first NON-COMPLETED state
                jobStepState = data[lineno][7]
                if re.match(r"(FAILED)|(CANCELLED)", jobStepState) and jobState == "COMPLETED":
                    jobState = jobStepState
                #  read line ? with "hydra_pmi_proxy" and find ntasks
                if re.search(r"^hydra_pmi_proxy", data[lineno][1]):
                    result.append(data[lineno][-2] if data[lineno][-2].isdigit() else "-1")
                    break
            if len(result) == 11:
                result.append("-1")
            result.append(jobState)
            result = pd.DataFrame([result], columns=attributes)
            return result
            

    # get raw data by sacct command
    def __get_raw_data(self, taskID):
        """
        Get accounting data and slurm script by sacct command.
         - Accounting data will be stored to : ./data/raw/sacct.jobid
         - Original script will be stored to : ./data/raw/script.jobid
        ---

        Attention : Running path should be : ./data/
        """

        SACCT_ACCT_COMMAND = f"sacct \
            --format jobid,jobname%25,elapsedraw,start,end,submit,suspended,state%25,priority,ntasks,alloctres%40 \
            -j {taskID} \
            > ./raw/sacct.{taskID}"
        SACCT_SCRIPT_COMMAND = f"sacct --batch-script -j {taskID} > ./raw/script.{taskID}"
        os.system(SACCT_ACCT_COMMAND)
        time.sleep(1)
        os.system(SACCT_SCRIPT_COMMAND)
        time.sleep(1)


