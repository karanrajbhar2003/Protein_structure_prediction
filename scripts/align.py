from modeller import *

log.verbose()
env = Environ()

# -- Read in the sequences
aln = Alignment(env)
mdl = Model(env, file="../data/2LZM")
aln.append_model(mdl, align_codes="2LZM", atom_files="../data/2LZM.pdb")

# Read the sequence from the FASTA file
seq = aln.append(file="../data/t4_lysozyme.fasta", align_codes="sp|P00720|LYSC_BPT4")

# -- Align them
aln.align2d()

# -- Write the alignment file
aln.write(file="alignment.ali", alignment_format="PIR")
