#!/usr/bin/env python
"""
Calculates Inner Composition Alignment for Inferring Directed Networks
a la Hempel et al 2011 Physical Review Letters.
"""

import numpy as np
import nibabel as nib
import epitome as epi
import matplotlib.pyplot as plt

def reorder_by_driver(driver, driven):
	"""
	Reorders timeseries of driver and driven variable by driver quicksort.
	"""
	idx_sort = np.argsort(driver, kind='quicksort')
	driver = driver[idx_sort]
	driven = driven[idx_sort]
	return driver, driven

def crossings(M_r, n, m, MU_r, delta, permu, weight):
    crops(M_r, n, m, MU_r, delta, o_init, *weight);
    for(i = 0; i < *m; i++)

        for(j = 0; j < *m; j++)

            # significance of coupling strength
            c_sig[(j * m) + i] += (MU_r[(j * *m) + i] >= 
               MU[(j * m) + i]) ? 1 : 0;
    
            # significance of coupling direction
            cd_sig[(j * m) + i] += ((MU_r[(j * m) + i]-MU_r[(i * *m) + j]) >= 
               (MU[(j * m) + i] - MU[(i * m) + j])) ?  1 : 0;    
        }
    }
# def main():

# this is just for testing
data, affine, header, dims = epi.utilites.loadnii('mean_RUN_filterVent.nii.gz')
voxels = [100000, 125000, 200000]
data = data[voxels, :]

# init output array
n_timeseries = np.shape(data)[0]
n_timepoints = np.shape(data)[1]
graph = np.zeros((n_timeseries, n_timeseries))

# init the sums
idx_i = np.arange(n_timepoints - 1)
idx_j = np.arange(n_timepoints - 1) + 1

# init parameters
delta = ((n_timepoints - 1) * (n_timepoints - 2)) / 2.0 # normalization constant
permu = 1 # for now, no permutations
weight = 1 # weight function

# loop through the graph
for x in np.arange(n_timeseries):
	for y in np.arange(n_timeseries):
		
		# reorder the driven variable by the driver timeseries
		if x == y:
			driver = None # self-to-self connectivity is always 1
		elif x > y:
			driver, driven = reorder_by_driver(data[x, :], data[y, :])
		elif x < y:
			driver, driven = reorder_by_driver(data[y, :], data[x, :])


        crossings = 

    	iota = np.sum(weight )

###
### C - template follows

#include <R.h>
#include <stdio.h>
#include <math.h>
#include <time.h>
#include "rngs.h"
#include "rvgs.h"


void quickSort( double a[], int l, int r, int o[]);
int partition( double a[], int l, int r, int o[]) ;
double cross( double g[], int n, double delta, int w); 
double Random(void);
void PlantSeeds(long x);
void PutSeed(long x);
void GetSeed(long *x);
void SelectStream(int index);
void TestRandom(void);
double Uniform(double a, double b);
void sample( int s[], int n);
void crops(double MM[], int nn, int mm, double mu[], double delta, int o_init[], int w);


void crossing(double *M, int *n, int *m, double *MU, double *MUsig, int *rmax, double *MUsigd, int *weight)
{ 
 double a[*n], g[*n], delta, M_r[(*n * *m)], MU_r[(*m * *m)]; 
 int o_init[*n], s[*n];
 int i, j, j1, j2, r, c_sig[(*m * *m)], cd_sig[(*m * *m)];

 /*
 #############################################################
 initial sequence (permutation)
 #############################################################
 */ 
 for(i = 0; i < *n; i++)
 {
  o_init[i] = (i+1);
 }
 /*
 #############################################################
 normalization constant
 #############################################################
 */  
 delta = (double)(*n-1) * (double)(*n-2) / 2.;
 /*
 #############################################################
 calculate crossing points 
 #############################################################
 */ 
 crops(M, *n, *m, MU, delta, o_init, *weight);
 /*
 #############################################################
 initialize sig counter
 #############################################################
 */ 
 for(i = 0; i < (*m * *m); i++)
 {
  c_sig[i] = 0; 
  cd_sig[i] = 0;  
 }
 /*
 #############################################################
 calculate significance of crossing points measure
 #############################################################
 */ 
 for(r = 0; r < *rmax; r++)
 {
  printf(" %d \n ", r);
  for(j1 = 0; j1 < *m; j1++)
  { 
   for(i = 0; i < *n; i++)
   {
    s[i] = (o_init[i]-1);
   }  
   /*
   #############################################################
   calculate random permutation
   #############################################################
   */
   sample( s, *n);
   /*
   #############################################################
   randomize time series 
   #############################################################
   */   
   for(i = 0; i < *n; i++)
   {
    M_r[((j1 * *n) + i)] = M[((j1 * *n) + s[i])];
   }  
  }
  /*
  #############################################################
  calculate crossing points for random series
  #############################################################
  */    
  crops(M_r, *n, *m, MU_r, delta, o_init, *weight);
  for(i = 0; i < *m; i++)
  {
   for(j = 0; j < *m; j++)
   {
    /*
    #############################################################
    significance of coupling strength
    #############################################################
    */    
    c_sig[(j * *m) + i] += (MU_r[(j * *m) + i] >= MU[(j * *m) + i]) ? 1 : 0;
    /*
    #############################################################
    significance of coupling direction
    #############################################################
    */ 
    cd_sig[(j * *m) + i] += ((MU_r[(j * *m) + i]-MU_r[(i * *m) + j]) >= (MU[(j * *m) + i]-MU[(i * *m) + j])) ?  1 : 0;    
   }
  }  
 }
 for(i = 0; i < (*m * *m); i++)
 {
  MUsig[i] = (double)(c_sig[i]+1)/(double)(*rmax+1);
  MUsigd[i] = (double)(cd_sig[i]+1)/(double)(*rmax+1);
 }
}



/*
#############################################################################################
#############################################################################################
######################################### subroutines  ######################################
#############################################################################################
#############################################################################################
*/

/*
#############################################################################################
########################### routines for measure evaluation #################################
#############################################################################################
*/
void crops(double MM[], int nn, int mm, double mu[], double delta, int o_init[], int w)
{ 
 double a[nn], g[nn];
 int o[nn], s[nn];
 int i, j1, j2;

 /*
 #############################################################
 loop for driving variable
 #############################################################
 */
 for(j1 = 0; j1 < mm; j1++)
 { 
  /*
  #############################################################
  extract time series of driving variable
  #############################################################
  */
  for(i = 0; i < nn; i++)
  {
   a[i] = MM[(j1 * nn)+i];
   o[i] = o_init[i];
  }  
  /*
  #############################################################
  sort time series of driving variable
  #############################################################
  */
  quickSort( a, 0, (nn-1), o); 
  /*
  #############################################################
  loop for driven variable
  #############################################################
  */  
  for(j2 = 0; j2 < mm; j2++)
  {
   /*
   #############################################################
   reorder time series of driven variable
   #############################################################
   */
   for(i = 0; i < nn; i++)
   {
    g[i] = MM[(j2 * nn)+(o[i]-1)];   
   }   
   /*
   #############################################################
   evaluate measures for j1 is driving j2
   #############################################################
   */
   mu[(j2 * mm)+j1] = cross( g, nn, delta, w);
  }
 }
}
/*
#############################################################################################
#############################################################################################
*/
#define MAX(a, b) ((a) > (b) ? (a) : (b))
double cross( double g[], int n, double delta, int w) 
{
  int tau,s;
  double omega = 0., mu;
   
  /* no weight */ 
  if(w == 0)
  {
   for(tau = 0; tau < (n-2); tau++)
   {
    for(s = (tau+1); s < (n-1); s++)
    {
     omega += ( (g[s+1] > g[tau] & g[s] < g[tau]) | (g[s+1] < g[tau] & g[s] > g[tau]) ) ? 1. : 0.;  
    }
   } 
  }
  /* slope */  
  if(w == 1)
  {
   for(tau = 0; tau < (n-2); tau++)
   {
    for(s = (tau+1); s < (n-1); s++)
    {
     omega += ( (g[s+1] > g[tau] & g[s] < g[tau]) | (g[s+1] < g[tau] & g[s] > g[tau]) ) ? (fabs(g[s+1]-g[s])) : 0.;  
    }
   } 
  } 
  /* squared slope */   
  if(w == 2)
  {
   for(tau = 0; tau < (n-2); tau++)
   {
    for(s = (tau+1); s < (n-1); s++)
    {
     omega += ( (g[s+1] > g[tau] & g[s] < g[tau]) | (g[s+1] < g[tau] & g[s] > g[tau]) ) ? ( (g[s+1]-g[s])*(g[s+1]-g[s]) ) : 0.;  
    }
   } 
  }
  /* arithmetic mean */   
  if(w == 3)
  {
   for(tau = 0; tau < (n-2); tau++)
   {
    for(s = (tau+1); s < (n-1); s++)
    {
     omega += ( (g[s+1] > g[tau] & g[s] < g[tau]) | (g[s+1] < g[tau] & g[s] > g[tau]) ) ? ( (g[s+1]+g[s])/2. ) : 0.;  
    }
   } 
  }
  /* geometric mean */  
  if(w == 4)
  {
   for(tau = 0; tau < (n-2); tau++)
   {
    for(s = (tau+1); s < (n-1); s++)
    {
     omega += ( (g[s+1] > g[tau] & g[s] < g[tau]) | (g[s+1] < g[tau] & g[s] > g[tau]) ) ? ( sqrt(g[s+1] * g[s]) ) : 0.;  
    }
   } 
  } 
  /* harmonic mean */
  if(w == 5)
  {
   for(tau = 0; tau < (n-2); tau++)
   {
    for(s = (tau+1); s < (n-1); s++)
    {
     omega += ( (g[s+1] > g[tau] & g[s] < g[tau]) | (g[s+1] < g[tau] & g[s] > g[tau]) ) ? ( (2./((1./g[s+1])+(1./g[s]))) ) : 0.;  
    }
   } 
  }   
  /* max */
  if(w == 6)
  {
   for(tau = 0; tau < (n-2); tau++)
   {
    for(s = (tau+1); s < (n-1); s++)
    {
     omega += ( (g[s+1] > g[tau] & g[s] < g[tau]) | (g[s+1] < g[tau] & g[s] > g[tau]) ) ? ( (MAX((fabs(g[s+1] - g[tau])), (fabs(g[s] - g[tau])))) ) : 0.;  
    }
   } 
  }      
   
  mu = 1. - (omega/delta);
  return(mu); 
}
/*
#############################################################################################
########################### routines for sorting process ####################################
#############################################################################################
*/
/*
#############################################################################################
#############################################################################################
*/
void quickSort( double a[], int l, int r, int o[])
{
   int j;

   if( l < r ) 
   {
       // divide and conquer
       j = partition( a, l, r, o);
       quickSort( a, l, j-1, o);
       quickSort( a, j+1, r, o);
   }
	
}
/*
#############################################################################################
#############################################################################################
*/
int partition( double a[], int l, int r, int o[]) 
{
   int i, j, tt; 
   double pivot, t;
   pivot = a[l];
   i = l; j = r+1;
		
   while( 1)
   {
   	do ++i; while( a[i] <= pivot && i <= r );
   	do --j; while( a[j] > pivot );
   	if( i >= j ) break;
   	t = a[i]; a[i] = a[j]; a[j] = t;
  	t = o[i]; o[i] = o[j]; o[j] = t;	
   }
   t = a[l]; a[l] = a[j]; a[j] = t;
   tt = o[l]; o[l] = o[j]; o[j] = tt;  
   return j;
}
/*
#############################################################################################
########################### routines for randomization process ##############################
#############################################################################################
*/
/*
#############################################################################################
#############################################################################################
*/
void sample( int s[], int n)
{
 int i;
 int nn = n;
 int t, tt; 
 
 for(i = 0; i < n; i++)
 {
  nn--;
  t = (int)round(Uniform(0., (double)nn));
  tt = s[t]; s[t] = s[nn]; s[nn] = tt;
 }
}
/*
#############################################################################################
#############################################################################################
*/
#define MODULUS    2147483647 /* DON'T CHANGE THIS VALUE                  */
#define MULTIPLIER 48271      /* DON'T CHANGE THIS VALUE                  */
#define CHECK      399268537  /* DON'T CHANGE THIS VALUE                  */
#define STREAMS    256        /* # of streams, DON'T CHANGE THIS VALUE    */
#define A256       22925      /* jump multiplier, DON'T CHANGE THIS VALUE */
#define DEFAULT    123456789  /* initial seed, use 0 < DEFAULT < MODULUS  */
      
static long seed[STREAMS] = {DEFAULT};  /* current state of each stream   */
static int  stream        = 0;          /* stream index, 0 is the default */
static int  initialized   = 0;          /* test for stream initialization */
/*
#############################################################################################
#############################################################################################
*/
   double Random(void)
/* ----------------------------------------------------------------
 * Random returns a pseudo-random real number uniformly distributed 
 * between 0.0 and 1.0. 
 * ----------------------------------------------------------------
 */
{
  const long Q = MODULUS / MULTIPLIER;
  const long R = MODULUS % MULTIPLIER;
        long t;

  t = MULTIPLIER * (seed[stream] % Q) - R * (seed[stream] / Q);
  if (t > 0) 
    seed[stream] = t;
  else 
    seed[stream] = t + MODULUS;
  return ((double) seed[stream] / MODULUS);
}
/*
#############################################################################################
#############################################################################################
*/
   void PlantSeeds(long x)
/* ---------------------------------------------------------------------
 * Use this function to set the state of all the random number generator 
 * streams by "planting" a sequence of states (seeds), one per stream, 
 * with all states dictated by the state of the default stream. 
 * The sequence of planted states is separated one from the next by 
 * 8,367,782 calls to Random().
 * ---------------------------------------------------------------------
 */
{
  const long Q = MODULUS / A256;
  const long R = MODULUS % A256;
        int  j;
        int  s;

  initialized = 1;
  s = stream;                            /* remember the current stream */
  SelectStream(0);                       /* change to stream 0          */
  PutSeed(x);                            /* set seed[0]                 */
  stream = s;                            /* reset the current stream    */
  for (j = 1; j < STREAMS; j++) {
    x = A256 * (seed[j - 1] % Q) - R * (seed[j - 1] / Q);
    if (x > 0)
      seed[j] = x;
    else
      seed[j] = x + MODULUS;
   }
}
/*
#############################################################################################
#############################################################################################
*/
   void PutSeed(long x)
/* ---------------------------------------------------------------
 * Use this function to set the state of the current random number 
 * generator stream according to the following conventions:
 *    if x > 0 then x is the state (unless too large)
 *    if x < 0 then the state is obtained from the system clock
 *    if x = 0 then the state is to be supplied interactively
 * ---------------------------------------------------------------
 */
{
  char ok = 0;

  if (x > 0)
    x = x % MODULUS;                       /* correct if x is too large  */
  if (x < 0)                                 
    x = ((unsigned long) time((time_t *) NULL)) % MODULUS;              
  if (x == 0)                                
    while (!ok) {
      printf("\nEnter a positive integer seed (9 digits or less) >> ");
      scanf("%ld", &x);
      ok = (0 < x) && (x < MODULUS);
      if (!ok)
        printf("\nInput out of range ... try again\n");
    }
  seed[stream] = x;
}
/*
#############################################################################################
#############################################################################################
*/
   void GetSeed(long *x)
/* ---------------------------------------------------------------
 * Use this function to get the state of the current random number 
 * generator stream.                                                   
 * ---------------------------------------------------------------
 */
{
  *x = seed[stream];
}
/*
#############################################################################################
#############################################################################################
*/
   void SelectStream(int index)
/* ------------------------------------------------------------------
 * Use this function to set the current random number generator
 * stream -- that stream from which the next random number will come.
 * ------------------------------------------------------------------
 */
{
  stream = ((unsigned int) index) % STREAMS;
  if ((initialized == 0) && (stream != 0))   /* protect against        */
    PlantSeeds(DEFAULT);                     /* un-initialized streams */
}
/*
#############################################################################################
#############################################################################################
*/
   void TestRandom(void)
/* ------------------------------------------------------------------
 * Use this (optional) function to test for a correct implementation.
 * ------------------------------------------------------------------    
 */
{
  long   i;
  long   x;
  double u;
  char   ok = 0;  

  SelectStream(0);                  /* select the default stream */
  PutSeed(1);                       /* and set the state to 1    */
  for(i = 0; i < 10000; i++)
    u = Random();
  GetSeed(&x);                      /* get the new state value   */
  ok = (x == CHECK);                /* and check for correctness */

  SelectStream(1);                  /* select stream 1                 */ 
  PlantSeeds(1);                    /* set the state of all streams    */
  GetSeed(&x);                      /* get the state of stream 1       */
  ok = ok && (x == A256);           /* x should be the jump multiplier */    
  if (ok)
    printf("\n The implementation of rngs.c is correct.\n\n");
  else
    printf("\n\a ERROR -- the implementation of rngs.c is not correct.\n\n");
}
/*
#############################################################################################
#############################################################################################
*/
   double Uniform(double a, double b)
/* =========================================================== 
 * Returns a uniformly distributed real number between a and b. 
 * NOTE: use a < b
 * ===========================================================
 */
{ 
  return (a + (b - a) * Random());
}

