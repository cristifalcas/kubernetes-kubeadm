import logging, os

logfile = os.path.abspath(os.path.dirname(os.path.realpath(__file__)) + '/../../') + '/kubeadm.log'
logging.getLogger().setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s :%(levelname)s:%(name)s:  %(message)s')

file = logging.FileHandler(logfile, mode = 'w')
file.setLevel(logging.INFO)
file.setFormatter(formatter)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(formatter)

logging.getLogger().addHandler(file)
logging.getLogger().addHandler(console)

logging.info("Writing logs to file %s" %logfile)
