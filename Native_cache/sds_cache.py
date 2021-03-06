'''
Created on 05/11/2013

@author: Raul
'''
from threading import Semaphore
import time

ENABLE_CACHE = True
#Cache size limit in bytes
CACHE_MAX_SIZE = 200*1024*1024*1024
available_policies = {"LRU", "LFU"}


class CacheObjectDescriptor(object):
    
    def __init__(self, block_id, size, etag):
        self.block_id = block_id
        self.last_access = time.time()
        self.get_hits = 0
        self.put_hits = 0
        self.num_accesses = 0
        self.size = size
        self.etag = etag
        
    def get_hit(self):
        self.get_hits += 1
        self.hit()
        
    def put_hit(self):
        self.put_hits += 1
        self.hit()
        
    def hit(self):        
        self.last_access = time.time()
        self.num_accesses += 1
   
   
class BlockCache(object):
    
    def __init__(self):
        #This will contain the actual data of each block
        self.descriptors_dict = {}
        #Structure to store the cache metadata of each block
        self.descriptors = [] 
        #Cache statistics
        self.get_hits = 0
        self.put_hits = 0
        self.misses = 0
        self.evictions = 0
        self.reads = 0
        self.writes = 0
        self.cache_size_bytes = 0
        
        #Eviction policy
        self.policy = "LFU"
        #Synchronize shared cache content
        self.semaphore = Semaphore()
        
    
    def access_cache(self, operation='PUT', block_id=None, block_data=None, etag=None):
        result = None
        if ENABLE_CACHE:
            self.semaphore.acquire()
            if operation == 'PUT':
                result = self._put(block_id, block_data, etag)
            elif operation == 'GET':
                result = self._get(block_id)
            else: raise Exception("Unsupported cache operation" + operation)
            #Sort descriptors based on eviction policy order
            self._sort_descriptors()
            self.semaphore.release()
        return result
                
    def _put(self, block_id, block_size, etag):
        self.writes+=1
        to_evict = [];
        #Check if the cache is full and if the element is new
        if CACHE_MAX_SIZE <= (self.cache_size_bytes + block_size) and block_id not in self.descriptors_dict:
            #Evict as many files as necessary until having enough space for new one
            while (CACHE_MAX_SIZE <= (self.cache_size_bytes + block_size)):
                #Get the last element ordered by the eviction policy
                self.descriptors, evicted = self.descriptors[:-1], self.descriptors[-1]
                #Reduce the size of the cache
                self.cache_size_bytes -= evicted.size
                #Icrease evictions count and add to
                self.evictions+=1
                to_evict.append(evicted.block_id);
                #Remove from evictions dict                
                del self.descriptors_dict[evicted.block_id]
            
        if block_id in self.descriptors_dict:
            descriptor = self.descriptors_dict[block_id]
            self.descriptors_dict[block_id].size = block_size
            self.descriptors_dict[block_id].etag = etag
            descriptor.put_hit()  
            self.put_hits += 1    
        else:
            #Add the new element to the cache
            descriptor = CacheObjectDescriptor(block_id, block_size, etag)
            self.descriptors.append(descriptor)
            self.descriptors_dict[block_id] = descriptor
            self.cache_size_bytes += block_size            
        
        assert len(self.descriptors) == len(self.descriptors_dict.keys()) ==\
            len(self.descriptors_dict.keys()), "Unequal length in cache data structures"
            
        return to_evict
        
    def _get(self, block_id):
        self.reads+=1
        if block_id in self.descriptors_dict: 
            self.descriptors_dict[block_id].get_hit()
            self.get_hits += 1 
            return block_id, self.descriptors_dict[block_id].size, self.descriptors_dict[block_id].etag
        self.misses+=1
        return None, 0, ''
    
    def _sort_descriptors(self):
        #Order the descriptor list depending on the policy
        if self.policy == "LRU":
            self.descriptors.sort(key=lambda desc: desc.last_access, reverse=True) 
        elif self.policy == "LFU":
            self.descriptors.sort(key=lambda desc: desc.get_hits, reverse=True)
        else: raise Exception("Unsupported caching policy.")
        
    def write_statistics(self, statistics_manager):
        if ENABLE_CACHE:
            statistics_manager.cache_state(self.get_hits, self.put_hits,
                self.misses, self.evictions, self.reads, self.writes, self.cache_size_bytes)
        
    def cache_state(self):
        print "CACHE GET HITS: " , self.get_hits
        print "CACHE PUT HITS: " , self.put_hits
        print "CACHE MISSES: ", self.misses
        print "CACHE EVICTIONS: ", self.evictions
        print "CACHE READS: ", self.reads
        print "CACHE WRITES: ", self.writes
        print "CACHE SIZE: ", self.cache_size_bytes
        
        for descriptor in self.descriptors:
            print "Object: ",  descriptor.block_id, descriptor.last_access, descriptor.get_hits, descriptor.put_hits, descriptor.num_accesses, descriptor.size
            